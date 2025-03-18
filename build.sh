#!/bin/bash
# 构建脚本，支持 install 和 zip 命令

function install_deps() {
    echo "安装依赖..."
    pip install -t . -r requirements.txt
    echo "依赖安装完成"
}

function zip_code() {
    echo "打包代码..."
    # 获取当前时间戳
    timestamp=$(date +%Y%m%d%H%M%S)
    # 获取git最近一次提交的前7位字符
    commit_hash=$(git rev-parse --short HEAD)

    # 创建 build 目录（如果不存在）
    mkdir -p build

    zip_filename="build/code-${timestamp}-${commit_hash}.zip"
    zip $zip_filename -r ./* -x "build/*"
    echo "代码已打包到: $zip_filename"
}

function show_help() {
    echo "使用方法:"
    echo "  $0 install    - 安装依赖"
    echo "  $0 zip        - 打包代码"
    echo "  $0 help       - 显示帮助信息"
}

case "$1" in
    install)
        install_deps
        ;;
    zip)
        zip_code
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        if [ -z "$1" ]; then
            echo "错误: 未指定命令"
        else
            echo "错误: 未知命令 '$1'"
        fi
        show_help
        exit 1
        ;;
esac


