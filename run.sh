#!/bin/bash

# 运行脚本，用于启动网关和工作节点

# 检查命令
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo "错误: 未找到 $1 命令"
        exit 1
    fi
}

# 检查必要的命令
check_command python3

# 定义颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # 无颜色

# 显示帮助
show_help() {
    echo -e "${BLUE}用法:${NC} $0 [命令]"
    echo ""
    echo "命令:"
    echo "  gate          启动网关服务"
    echo "  worker        启动一个工作节点"
    echo "  worker-v1     启动版本为v1的工作节点"
    echo "  worker-v2     启动版本为v2的工作节点"
    echo "  multi         启动网关和多个工作节点"
    echo "  test          运行单元测试"
    echo "  help          显示此帮助信息"
    echo ""
}

# 启动网关
start_gate() {
    echo -e "${GREEN}启动网关服务...${NC}"
    python3 gate.py
}

# 启动工作节点
start_worker() {
    local version=$1
    if [ -n "$version" ]; then
        echo -e "${GREEN}启动工作节点 (版本: $version)...${NC}"
        python3 worker.py --version $version
    else
        echo -e "${GREEN}启动工作节点...${NC}"
        python3 worker.py
    fi
}

# 启动多个服务
start_multi() {
    echo -e "${YELLOW}启动多服务模式...${NC}"
    
    # 启动网关
    echo -e "${GREEN}启动网关服务 (后台)...${NC}"
    python3 gate.py > logs/gate.log 2>&1 &
    GATE_PID=$!
    echo "网关服务 PID: $GATE_PID"
    
    # 等待网关启动
    sleep 2
    
    # 启动版本为v1的工作节点
    echo -e "${GREEN}启动工作节点 v1 (后台)...${NC}"
    python3 worker.py --version v1 > logs/worker-v1.log 2>&1 &
    WORKER1_PID=$!
    echo "工作节点 v1 PID: $WORKER1_PID"
    
    # 启动版本为v2的工作节点
    echo -e "${GREEN}启动工作节点 v2 (后台)...${NC}"
    python3 worker.py --version v2 > logs/worker-v2.log 2>&1 &
    WORKER2_PID=$!
    echo "工作节点 v2 PID: $WORKER2_PID"
    
    echo -e "${YELLOW}所有服务已启动，按 Ctrl+C 停止${NC}"
    
    # 创建 PID 文件
    mkdir -p .pid
    echo $GATE_PID > .pid/gate.pid
    echo $WORKER1_PID > .pid/worker-v1.pid
    echo $WORKER2_PID > .pid/worker-v2.pid
    
    # 等待中断信号
    trap "kill $GATE_PID $WORKER1_PID $WORKER2_PID; rm -f .pid/*; echo -e '${YELLOW}已停止所有服务${NC}'; exit 0" INT
    
    # 保持脚本运行
    while true; do
        sleep 1
    done
}

# 运行测试
run_tests() {
    echo -e "${GREEN}运行单元测试...${NC}"
    python3 -m unittest discover tests
}

# 创建日志目录
mkdir -p logs

# 处理命令
case "$1" in
    gate)
        start_gate
        ;;
    worker)
        start_worker
        ;;
    worker-v1)
        start_worker "v1"
        ;;
    worker-v2)
        start_worker "v2"
        ;;
    multi)
        start_multi
        ;;
    test)
        run_tests
        ;;
    help|*)
        show_help
        ;;
esac 