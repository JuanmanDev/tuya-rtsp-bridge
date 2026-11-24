package rtsp

import (
	"net"
	"strconv"
	"strings"
	"testing"

	"tuya-ipc-terminal/pkg/storage"
)

func testCamera(audioCodec int) *storage.CameraInfo {
	skill := `{"webrtc":1,"videos":[{"streamType":2,"codecType":2,"width":1920,"height":1080}],` +
		`"audios":[{"channels":1,"dataBit":16,"codecType":` + strconv.Itoa(audioCodec) + `,"sampleRate":8000}]}`
	return &storage.CameraInfo{DeviceID: "dev1", DeviceName: "Cam", Skill: skill}
}

func TestWantsBackchannel(t *testing.T) {
	cases := []struct {
		name    string
		headers map[string]string
		want    bool
	}{
		{"no headers", map[string]string{}, false},
		{"VLC", map[string]string{"User-Agent": "VLC/3.0.20 LibVLC/3.0.20"}, false},
		{"go2rtc", map[string]string{"User-Agent": "go2rtc/1.9.14"}, true},
		{"go2rtc lower-case header name", map[string]string{"user-agent": "go2rtc/1.9.14"}, true},
		{"ONVIF Require", map[string]string{"Require": "www.onvif.org/ver20/backchannel"}, true},
		{"unrelated Require", map[string]string{"Require": "some-other-extension"}, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := wantsBackchannel(tc.headers); got != tc.want {
				t.Errorf("wantsBackchannel(%v) = %v, want %v", tc.headers, got, tc.want)
			}
		})
	}
}

// Plain RTSP players (VLC, LIVE555) must keep getting the receive-only SDP.
func TestSDPWithoutBackchannelIsUnchanged(t *testing.T) {
	s := &RTSPServer{}
	sdp := s.generateSDP(testCamera(101), "rtsp://10.0.0.2:8554/Cam/hd", "hd", false)

	if strings.Contains(sdp, "sendonly") || strings.Contains(sdp, "/backchannel") {
		t.Fatalf("SDP without backchannel request must not contain a backchannel:\n%s", sdp)
	}
	if n := strings.Count(sdp, "m=audio"); n != 1 {
		t.Fatalf("expected exactly 1 audio m-line, got %d:\n%s", n, sdp)
	}
	if !strings.Contains(sdp, "a=control:rtsp://10.0.0.2:8554/Cam/hd/audio\r\n") {
		t.Fatalf("missing audio control URL:\n%s", sdp)
	}
}

// go2rtc / Frigate ask for the backchannel: expose a sendonly G.711 audio m-line.
func TestSDPWithBackchannel(t *testing.T) {
	s := &RTSPServer{}
	sdp := s.generateSDP(testCamera(101), "rtsp://10.0.0.2:8554/Cam/hd", "hd", true)

	if n := strings.Count(sdp, "m=audio"); n != 2 {
		t.Fatalf("expected 2 audio m-lines (recv + backchannel), got %d:\n%s", n, sdp)
	}
	idx := strings.Index(sdp, "a=control:rtsp://10.0.0.2:8554/Cam/hd/backchannel\r\n")
	if idx < 0 {
		t.Fatalf("missing backchannel control URL:\n%s", sdp)
	}
	// The sendonly attribute belongs to the backchannel media (after its control line).
	if !strings.Contains(sdp[idx:], "a=sendonly\r\n") {
		t.Fatalf("backchannel media is not sendonly:\n%s", sdp)
	}
	if !strings.Contains(sdp, "a=rtpmap:0 PCMU/8000\r\n") {
		t.Fatalf("expected PCMU rtpmap for camera codec 101:\n%s", sdp)
	}
}

func TestSDPBackchannelFollowsPCMA(t *testing.T) {
	s := &RTSPServer{}
	sdp := s.generateSDP(testCamera(106), "rtsp://h/Cam/hd", "hd", true)

	if n := strings.Count(sdp, "a=rtpmap:8 PCMA/8000\r\n"); n != 2 {
		t.Fatalf("expected PCMA on both audio m-lines, found %d:\n%s", n, sdp)
	}
}

// DESCRIBE over a real connection: the request headers decide whether the
// sendonly backchannel is in the SDP that goes back on the wire.
func TestDescribeAdvertisesBackchannelOnRequest(t *testing.T) {
	cases := []struct {
		name    string
		headers map[string]string
		want    bool
	}{
		{"plain player", map[string]string{}, false},
		{"go2rtc backchannel", map[string]string{"User-Agent": "go2rtc/1.9.14"}, true},
		{"ONVIF Require", map[string]string{"Require": "www.onvif.org/ver20/backchannel"}, true},
		{"VLC", map[string]string{"User-Agent": "VLC/3.0.20 LibVLC/3.0.20"}, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			server, client := net.Pipe()
			defer server.Close()
			defer client.Close()

			stream := &CameraStream{camera: testCamera(101), resolution: "hd"}
			rc := &RTSPClient{conn: server, stream: stream}
			req := &RTSPRequest{Method: "DESCRIBE", URL: "rtsp://h:8554/Cam/hd", CSeq: 2, Headers: tc.headers}

			done := make(chan []byte, 1)
			go func() {
				var out []byte
				tmp := make([]byte, 4096)
				for {
					m, err := client.Read(tmp)
					out = append(out, tmp[:m]...)
					if err != nil || strings.Contains(string(out), "\r\n\r\n") && bodyComplete(out) {
						break
					}
				}
				done <- out
			}()

			(&RTSPServer{}).handleDescribe(rc, req)
			resp := string(<-done)
			if !strings.Contains(resp, "200 OK") {
				t.Fatalf("DESCRIBE not 200:\n%s", resp)
			}
			if got := strings.Contains(resp, "a=sendonly"); got != tc.want {
				t.Fatalf("sendonly backchannel in SDP = %v, want %v:\n%s", got, tc.want, resp)
			}
		})
	}
}

// bodyComplete reports whether the Content-Length body after the headers is fully read.
func bodyComplete(out []byte) bool {
	s := string(out)
	head := strings.Index(s, "\r\n\r\n")
	if head < 0 {
		return false
	}
	for _, line := range strings.Split(s[:head], "\r\n") {
		if strings.HasPrefix(line, "Content-Length: ") {
			n, err := strconv.Atoi(strings.TrimPrefix(line, "Content-Length: "))
			return err == nil && len(s)-(head+4) >= n
		}
	}
	return true
}
