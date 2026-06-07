#!/bin/bash
# 小红书搜索环境一键安装脚本
# 在 root 权限的容器中运行

set -e

echo "🐱 Miya 开始安装小红书搜索环境..."

# 1. 安装系统依赖
echo "📦 安装系统依赖..."
apt-get update -qq
apt-get install -y -qq python3-pip python3-venv

# 2. 创建虚拟环境
echo "🐍 创建 Python 虚拟环境..."
python3 -m venv /opt/xhs-env

# 3. 安装 xhs-cli
echo "📕 安装 xiaohongshu-cli..."
/opt/xhs-env/bin/pip install xiaohongshu-cli

# 4. 验证安装
echo "✅ 验证安装..."
/opt/xhs-env/bin/xhs --version

echo ""
echo "🎉 安装完成！"
echo "使用方式: /opt/xhs-env/bin/xhs search '关键词'"
echo "登录方式: /opt/xhs-env/bin/xhs login --cookie-source chrome"
echo "状态检查: /opt/xhs-env/bin/xhs status"
