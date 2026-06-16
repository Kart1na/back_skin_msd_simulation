# LSCURE AI 报告服务 Ubuntu 16 安装说明

交付文件：

```text
lscure-ai-report-server-ubuntu16.run
```

## 安装

在 Ubuntu 16 终端中进入安装包所在目录，执行：

```bash
chmod +x lscure-ai-report-server-ubuntu16.run
./lscure-ai-report-server-ubuntu16.run
```

## 启动

安装完成后执行：

```bash
~/.local/bin/lscure-ai-report-server
```

看到服务启动提示后，浏览器打开：

```text
http://127.0.0.1:9090/reports
```

机器人接口地址：

```text
POST http://<Ubuntu机器IP>:9090/ai-report/force
```

## 修改端口

```bash
AI_REPORT_PORT=9000 ~/.local/bin/lscure-ai-report-server
```

## 卸载

```bash
./lscure-ai-report-server-ubuntu16.run --uninstall
```
