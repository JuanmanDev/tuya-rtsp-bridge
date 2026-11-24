# Upstream: seydx/tuya-ipc-terminal

This directory is a **vendored copy** of

https://github.com/seydx/tuya-ipc-terminal

| | |
|---|---|
| License | MIT — see `LICENSE` (Copyright (c) 2025 seydx) |
| Upstream tag / message | 0.0.6 / `update version to 0.0.6` |
| Git commit | `d65b3e9babb4829176290b4d53195d62636f00bf` |
| Author | seydx &lt;dev@seydx.com&gt; |
| Date | 2025-05-31 |

Please prefer contributing engine fixes **upstream** when they are not
specific to this Windows GUI.

## Local patches (this project)

Applied on top of `d65b3e9`. Kept small on purpose.

1. **`pkg/rtsp/protocol.go`** — SDP uses the URL resolution (`hd` / `sd`)
   instead of always advertising HD. The `sendonly` backchannel audio track
   is only added for go2rtc clients (`User-Agent: go2rtc/…`, which Frigate
   bundles) and ONVIF clients (`Require: …/backchannel`). Plain RTSP clients
   (VLC/LIVE555) keep the receive-only SDP.
2. **`pkg/rtsp/bridge.go`** — the backchannel track is bound from the
   negotiated answer (`ensureBackchannel`), not only from `OnTrack`, and is
   accessed under a mutex.
3. **`pkg/rtsp/server.go`** — do not hold the stream mutex across the
   WebRTC dial (deadlock / stall when several cameras start).
4. **`pkg/storage/manager.go`** — look for `.tuya-data` in the process
   working directory, `%LOCALAPPDATA%\tuya-ipc-terminal`, and the user
   profile, not only `cwd/.tuya-data`.
5. **`cmd/cameras/cameras.go`** — treat doorbells / `sp_*` / p2p devices as
   cameras; do not drop a device if WebRTC config fails.
6. **`go.mod` / `go.sum`** — dependencies bumped with `go get -u ./... && go mod tidy`
   (pion/webrtc 4.2.x, golang.org/x/* current; module now requires Go 1.26+). No source changes.

Re-apply after an upstream pull:

```bat
git -C vendor\tuya-ipc-terminal remote add upstream https://github.com/seydx/tuya-ipc-terminal.git
git -C vendor\tuya-ipc-terminal fetch upstream
```

Then merge/rebase and restore the touched files if they conflict.
