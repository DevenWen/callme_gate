#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from flask import Flask, jsonify, request
import time

# 导入自定义模块
from lib.router.http_job_router import init_app as init_http_job_router, process_via_gateway, capture_http_job
from lib.router.route_registry import route_registry


# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

# 创建Flask应用
app = Flask(__name__)

# 初始化HTTP作业路由
init_http_job_router(app)

# 健康检查端点
@app.route("/health", methods=["GET"])
def health_check():
    """健康检查端点"""
    return jsonify({
        "status": "healthy",
        "timestamp": time.time()
    })

# 路由信息端点
@app.route("/routes", methods=["GET"])
def get_routes():
    """获取所有注册的路由信息"""
    routes = route_registry.get_all_routes()
    route_count = len(routes)
    
    route_info = []
    for route_id, route in routes.items():
        method, path = route_id.split(":", 1)
        route_info.append({
            "method": method,
            "path": path,
            "versions": route.versions if hasattr(route, 'versions') else [],
            "timeout": route.timeout if hasattr(route, 'timeout') else 30
        })
    
    return jsonify({
        "total_routes": route_count,
        "routes": route_info
    })

# 通用API路由器 - 处理所有 /api 路径下的请求
@app.route("/api/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@process_via_gateway(expire=60)
def api_router(subpath):
    """通用API路由器，将请求转发给工作节点处理
    
    Args:
        subpath: API子路径
        
    Returns:
        工作节点的处理结果
    """
    # 实际处理由 process_via_gateway 装饰器和工作节点完成
    pass

if __name__ == "__main__":
    logger.info("启动Gateway服务，端口9000")
    app.run(host='0.0.0.0', port=9000, debug=True) 