# noVNC 원격 오디오 스트림

TigerVNC/noVNC의 화면 연결과 별도로, 서버의 PipeWire-Pulse 출력 monitor를
프로젝트 전용 ffmpeg로 MP3 변환해 Tailscale 주소에 제공합니다.

## 접속

로컬 PC 브라우저의 새 탭에서 다음 주소 중 하나를 엽니다.

```text
http://100.113.15.83:8001
https://aim-dev-server.taile1bac9.ts.net/
```

브라우저 정책 때문에 자동 재생되지 않으면 페이지의 재생 버튼을 누릅니다.
브라우저가 연결될 때 프로젝트 전용 ffmpeg 프로세스가 시작되므로 접속 전에
쌓인 오래된 오디오를 재생하지 않습니다.

## 서비스 관리

```bash
systemctl --user status novnc-audio-stream.service
systemctl --user restart novnc-audio-stream.service
systemctl --user stop novnc-audio-stream.service
journalctl --user -u novnc-audio-stream.service -f
```

`8000`은 Audio2Face NIM이 사용하므로 내부 오디오 스트림은 `8001`을 사용합니다.
오디오 서버는 localhost에만 바인딩되고 Tailscale Serve가 HTTPS와 tailnet 전용
TCP `8001`로 프록시합니다. 따라서 일반 인터넷에는 노출하지 않습니다.

## 프로젝트 전용 ffmpeg

시스템 ffmpeg 패키지는 설치하지 않습니다. 실행기는 다음 위치에 있습니다.

```text
.tools/ffmpeg/bin/ffmpeg
```

`.tools/`는 Git에서 제외되어 있으며 Ubuntu ffmpeg 패키지에서 추출한 바이너리와
필요한 공유 라이브러리만 포함합니다.
