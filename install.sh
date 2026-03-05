#!/bin/bash

# ==========================================
# Xray Traffic Hub 一键部署脚本 (GitHub 版)
# ==========================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
PLAIN='\033[0m'
APP_DIR="/opt/traffic_monitor"
REPO_URL="https://github.com/你的用户名/xray-traffic-hub.git" # ⚠️ 请改成你的真实仓库地址

# 1. 检查 Root 权限
[[ $EUID -ne 0 ]] && echo -e "${RED}错误: 必须使用 root 用户运行此脚本！${PLAIN}" && exit 1

echo -e "${GREEN}>>> 1. 正在更新系统并安装基础环境 (Git, Python3-Venv)...${PLAIN}"
if [ -f /etc/debian_version ]; then 
    apt update && apt install -y git python3 python3-pip python3-venv curl
elif [ -f /etc/redhat-release ]; then 
    yum install -y git python3 python3-pip curl
fi

echo -e "${GREEN}>>> 2. 正在拉取最新的 GitHub 代码...${PLAIN}"
systemctl stop traffic_hub 2>/dev/null
# 如果目录已存在，则拉取最新代码；如果不存在，则克隆
if [ -d "$APP_DIR/.git" ]; then
    cd $APP_DIR && git pull
else
    rm -rf $APP_DIR
    git clone $REPO_URL $APP_DIR
fi

echo -e "${GREEN}>>> 3. 正在构建 Python 独立虚拟环境...${PLAIN}"
cd $APP_DIR
# 创建持久化数据目录
mkdir -p $APP_DIR/data

python3 -m venv venv
# 激活虚拟环境并安装 requirements.txt 里的依赖
$APP_DIR/venv/bin/pip install --upgrade pip
$APP_DIR/venv/bin/pip install -r requirements.txt

echo -e "${GREEN}>>> 4. 正在注册系统守护进程 (Systemd)...${PLAIN}"
cat << EOF > /etc/systemd/system/traffic_hub.service
[Unit]
Description=Xray Traffic Hub Server
After=network.target

[Service]
User=root
WorkingDirectory=$APP_DIR
# 使用虚拟环境的 Python，彻底隔离宿主机
ExecStart=$APP_DIR/venv/bin/python $APP_DIR/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable traffic_hub
systemctl restart traffic_hub

echo -e "${GREEN}==============================================${PLAIN}"
echo -e "${GREEN}✅ 部署圆满成功！${PLAIN}"
echo -e "Web 面板已在后台运行 (默认端口 5000)"
echo -e "如果你需要修改默认账号(admin)或密码，请编辑: ${YELLOW}$APP_DIR/app.py${PLAIN}"
echo -e "然后重启服务: ${YELLOW}systemctl restart traffic_hub${PLAIN}"
echo -e "${GREEN}==============================================${PLAIN}"
