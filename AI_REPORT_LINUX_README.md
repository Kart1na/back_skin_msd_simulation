# LSCURE AI 报告后台 Linux 部署说明

## 1. 启动后台

在 Linux 终端进入项目根目录：

```bash
cd /path/to/back_skin_msd_simulation-main
chmod +x start_ai_report_server.sh
./start_ai_report_server.sh
```

默认监听：

```text
0.0.0.0:9090
```

## 2. 查看报告

如果在同一台 Linux 机器上打开浏览器：

```text
http://127.0.0.1:9090/reports
```

如果在局域网其他电脑上查看，把 `<linux-ip>` 换成 Linux 机器 IP：

```text
http://<linux-ip>:9090/reports
```

## 3. 机器人调用接口

机器人软件向 Linux 后台发送：

```text
POST http://<linux-ip>:9090/ai-report/force
```

请求 JSON：

```json
{
  "pointCloudPath": "/data/xxxxx/pointCloud.txt",
  "acuCloPath": "/data/xxxxx/rgbImage_back_acu_pointcloud.txt",
  "robotPosToCameraPath": "/data/xxxxx/camera_posData_tcp.txt"
}
```

注意：这里的路径必须是 Linux 系统上真实存在的绝对路径。

成功返回：

```json
{
  "success": true,
  "message": "执行成功",
  "code": "0",
  "data": {
    "url": "http://<linux-ip>:9090/reports/xxxx.html"
  }
}
```

## 4. 可选配置

修改端口：

```bash
AI_REPORT_PORT=9000 ./start_ai_report_server.sh
```

指定 Python：

```bash
PYTHON_BIN=/usr/bin/python3 ./start_ai_report_server.sh
```

只允许本机访问：

```bash
AI_REPORT_HOST=127.0.0.1 ./start_ai_report_server.sh
```
