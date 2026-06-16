# Ubuntu 16 direct-run packaging

This project uses Python 3.7+ syntax and binary Python packages such as numpy,
scipy, matplotlib, Pillow, and reportlab. Ubuntu 16 usually ships Python 3.5,
so do not ship the Windows zip directly and expect it to run on Ubuntu 16.

Build the release package on Ubuntu 16, or in an Ubuntu 16 Docker/container
environment, so the generated executable is compatible with glibc 2.23.

## Build

Install Python 3.7 on the Ubuntu 16 build machine, then run:

```bash
cd /path/to/back_skin_msd_simulation-main
chmod +x packaging/package_ubuntu16.sh
PYTHON_BIN=/usr/bin/python3.7 packaging/package_ubuntu16.sh
```

The outputs are:

```text
build/ubuntu16/lscure-ai-report-server-ubuntu16.tar.gz
build/ubuntu16/lscure-ai-report-server-ubuntu16.run
```

## Run on the target Ubuntu 16 machine

Copy the `.run` installer to the target machine:

```bash
chmod +x lscure-ai-report-server-ubuntu16.run
./lscure-ai-report-server-ubuntu16.run
~/.local/bin/lscure-ai-report-server
```

The installer places the app in:

```text
~/.local/share/lscure-ai-report-server/
```

It also creates:

```text
~/.local/bin/lscure-ai-report-server
~/.local/share/applications/lscure-ai-report-server.desktop
```

The tarball can still be used manually:

```bash
tar -xzf lscure-ai-report-server-ubuntu16.tar.gz
cd lscure-ai-report-server-ubuntu16
./start_server.sh
```

Default service address:

```text
http://127.0.0.1:9090/reports
POST http://<linux-ip>:9090/ai-report/force
```

Optional port and host:

```bash
AI_REPORT_PORT=9000 ~/.local/bin/lscure-ai-report-server
AI_REPORT_HOST=127.0.0.1 AI_REPORT_PORT=9000 ~/.local/bin/lscure-ai-report-server
```

Uninstall:

```bash
./lscure-ai-report-server-ubuntu16.run --uninstall
```

## Notes

- Build on Ubuntu 16 for maximum compatibility. Building on Ubuntu 20/22/24 may
  produce binaries that fail on Ubuntu 16 with glibc errors.
- The packaged executable bundles Python, the application code, and third-party
  dependencies. Boss-side users do not need to run source files.
- Generated reports are written inside:

```text
~/.local/share/lscure-ai-report-server/_internal/lscure_report_interface/generated_reports/
```

- If the target server needs Chinese fonts for PDF/image rendering, install one
  of these on the Ubuntu 16 machine:

```bash
sudo apt-get install fonts-wqy-microhei
```

## Quick API test

Use the demo files after the server starts:

```bash
curl -X POST "http://127.0.0.1:9090/ai-report/force" \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "api_demo",
    "pointCloudPath": "'"$HOME"'/.local/share/lscure-ai-report-server/_internal/back_skin_msd_simulation/user_data/api_demo_pointCloud.txt",
    "acuCloPath": "'"$HOME"'/.local/share/lscure-ai-report-server/_internal/back_skin_msd_simulation/user_data/api_demo_acupoints.txt",
    "robotPosToCameraPath": "'"$HOME"'/.local/share/lscure-ai-report-server/_internal/back_skin_msd_simulation/user_data/api_demo_robot_trajectory.txt"
  }'
```
