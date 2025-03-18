#!/usr/bin/env python
# -*- coding: utf-8 -*-

from flask import request, Response, Blueprint, jsonify, current_app
import json
import time
from functools import wraps
from typing import Callable, Dict, Any, Optional, Union

from ..model.http_job import HttpJob, JobStatus
from ..model.job_repository import http_job_repository
from ..redis_client import RedisClient
from . import route_registry, job_dispatcher, Node, NodeStatus

# 创建蓝图
http_job_bp = Blueprint('http_job', __name__)

# Redis客户端实例
redis_client = RedisClient()

# 任务队列名称
TASK_QUEUE = "job_queue"

# 最大轮询时间（秒）
MAX_POLL_TIME = 30
# 轮询间隔（秒）
POLL_INTERVAL = 0.5

def _get_request_data() -> Dict[str, Any]:
    """获取当前请求的所有数据
    
    从Flask的request对象中提取所有相关数据
    
    Returns:
        包含请求数据的字典
    """
    headers = dict(request.headers)
    
    # 尝试获取各种请求体形式，使用force=False避免消耗请求流
    form_data = request.form.to_dict() if request.form else None
    
    try:
        if request.is_json:
            # 使用 force=False 和 silent=True 确保不消耗请求流并忽略错误
            json_data = request.get_json(force=False, silent=True)
        else:
            json_data = None
    except:
        json_data = None
    
    return {
        'method': request.method,
        'path': request.path,
        'headers': headers,
        'query_params': request.args.to_dict(flat=False),
        'form_data': form_data,
        'json_data': json_data
    }

def enqueue_task(request_id: str) -> bool:
    """将任务添加到队列
    
    Args:
        request_id: 任务ID
        
    Returns:
        是否成功添加
    """
    try:
        # 使用RPUSH添加到队列末尾
        redis_client.client.rpush(TASK_QUEUE, request_id)
        current_app.logger.info(f"任务 {request_id} 已加入队列")
        return True
    except Exception as e:
        current_app.logger.error(f"添加任务到队列失败: {e}")
        return False

def poll_job_result(request_id: str, timeout: int = MAX_POLL_TIME) -> Optional[HttpJob]:
    """轮询等待任务处理结果
    
    Args:
        request_id: 任务ID
        timeout: 最大等待时间（秒）
        
    Returns:
        处理完成的任务，或None（超时）
    """
    start_time = time.time()
    current_app.logger.info(f"开始轮询任务 {request_id} 的结果")
    
    while (time.time() - start_time) < timeout:
        # 获取当前任务状态
        job = http_job_repository.get(request_id)
        
        if job is None:
            current_app.logger.error(f"任务 {request_id} 不存在")
            return None
            
        # 如果任务已完成或失败，返回结果
        if job.status == JobStatus.COMPLETED or job.status == JobStatus.FAILED:
            current_app.logger.info(f"任务 {request_id} 已完成，状态: {job.status}")
            return job
            
        # 等待一段时间后继续轮询
        time.sleep(POLL_INTERVAL)
    
    # 超时
    current_app.logger.warning(f"等待任务 {request_id} 超时")
    return None

def process_via_gateway(expire: Optional[int] = None):
    """将HTTP请求转发到Worker处理的装饰器
    
    Args:
        expire: 任务过期时间（秒）
        
    Returns:
        装饰后的函数
    """
    def decorator(f: Callable):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # 获取请求数据
            job_data = _get_request_data()
            
            # 创建任务
            job = HttpJob(**job_data)
            job.update_status(JobStatus.PENDING)
            
            # 记录开始处理时间
            start_time = time.time()
            current_app.logger.info(f"收到请求: {job.request_id}, 路径: {job.path}, 方法: {job.method}")
            
            # 检查路由是否已注册
            route = route_registry.get_route(job.path, job.method)
            if not route or not route.get_workers():
                return jsonify({
                    "error": f"无法找到处理 {job.method} {job.path} 的服务",
                    "request_id": job.request_id
                }), 404
            
            # 保存任务到Redis
            if not http_job_repository.save(job, expire):
                return jsonify({
                    "error": "无法保存任务", 
                    "request_id": job.request_id
                }), 500
                
            # 从请求头中获取可能的路由版本或其他路由信息
            request_headers = dict(request.headers)
            routing_data = {}
            
            # 如果请求头中指定了特定版本，添加到路由数据中
            if 'X-API-Version' in request_headers:
                routing_data['version'] = request_headers['X-API-Version']
                
            # 分发任务到对应的工作队列
            success, worker = job_dispatcher.dispatch_job(job.request_id, job.path, job.method, routing_data)
            if not success:
                return jsonify({
                    "error": "无法分发任务到工作队列", 
                    "request_id": job.request_id
                }), 500
            
            # 获取路由的超时设置
            timeout = route_registry.get_route_timeout(job.path, job.method)
            
            # 等待处理结果
            result_json = job_dispatcher.wait_for_result(job.request_id, timeout)
            
            # 计算处理时间
            processing_time = time.time() - start_time
            current_app.logger.info(f"请求处理时间: {processing_time:.4f}秒, ID: {job.request_id}")
            
            # 处理超时
            if result_json is None:
                return jsonify({
                    "error": f"处理超时, 处理时间超过: {processing_time:.4f}秒", 
                    "request_id": job.request_id
                }), 504
                
            # 解析结果
            try:
                result_job = HttpJob.from_dict(json.loads(result_json))
            except Exception as e:
                current_app.logger.error(f"解析处理结果时发生错误: {e}")
                return jsonify({
                    "error": "无法解析处理结果", 
                    "request_id": job.request_id
                }), 500
                
            # 任务失败
            if result_job.status == JobStatus.FAILED:
                return jsonify({
                    "error": result_job.error_message or "任务处理失败", 
                    "request_id": result_job.request_id
                }), 500
                
            # 返回处理结果
            if result_job.response_body:
                response = jsonify(result_job.response_body)
                response.status_code = result_job.response_status or 200
            else:
                response = jsonify({
                    "message": "处理成功", 
                    "request_id": result_job.request_id
                })
                
            # 添加请求ID和工作节点信息到响应头
            response.headers['X-Request-ID'] = job.request_id
            if worker:
                response.headers['X-Worker-ID'] = worker.get('worker_id', '')
                response.headers['X-Worker-Version'] = worker.get('version', '')
            
            return response
            
        return wrapper
    return decorator

# 保留原始装饰器，用于测试和调试
def capture_http_job(expire: Optional[int] = None):
    """用于捕获HTTP请求并将其作为Job保存的装饰器
    
    Args:
        expire: 作业过期时间（秒）
        
    Returns:
        装饰后的函数
    """
    def decorator(f: Callable):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # 创建HTTP作业对象
            job_data = _get_request_data()
            job = HttpJob(**job_data)
            
            start_time = time.time()
            
            try:
                # 执行原始处理函数
                response = f(*args, **kwargs)
                
                # 如果返回的不是 Response 对象，转换为 Response
                if not isinstance(response, Response):
                    if isinstance(response, dict) or isinstance(response, list):
                        response = jsonify(response)
                    else:
                        response = Response(response)
                
                # 记录响应信息
                response_body = None
                
                # 尝试解析响应体为 JSON
                if response.is_json:
                    response_body = response.get_json()
                elif hasattr(response, 'data') and response.data:
                    try:
                        response_body = json.loads(response.data.decode('utf-8'))
                    except:
                        response_body = response.data.decode('utf-8')
                
                # 设置作业的响应信息
                job.set_response(
                    status=response.status_code,
                    headers=dict(response.headers),
                    body=response_body
                )
                
            except Exception as e:
                # 记录错误信息
                current_app.logger.exception("处理请求时发生错误")
                job.set_error(str(e))
                
                # 重新抛出异常，让Flask处理错误
                raise
            
            finally:
                # 计算处理时间并保存作业
                processing_time = time.time() - start_time
                current_app.logger.info(f"请求处理时间: {processing_time:.4f}秒, ID: {job.request_id}")
                
                # 保存作业到Redis
                http_job_repository.save(job, expire)
            
            # 在响应头中添加请求ID，方便跟踪
            if isinstance(response, Response):
                response.headers['X-Request-ID'] = job.request_id
            
            return response
        return wrapper
    return decorator

@http_job_bp.route('/jobs/<request_id>', methods=['GET'])
def get_job(request_id: str):
    """获取指定ID的作业信息
    
    Args:
        request_id: 请求ID
        
    Returns:
        作业信息或错误信息
    """
    job = http_job_repository.get(request_id)
    
    if job is None:
        return jsonify({"error": "作业不存在"}), 404
        
    return jsonify(job.to_dict())

@http_job_bp.route('/jobs/<request_id>', methods=['DELETE'])
def delete_job(request_id: str):
    """删除指定ID的作业
    
    Args:
        request_id: 请求ID
        
    Returns:
        成功或错误信息
    """
    if not http_job_repository.exists(request_id):
        return jsonify({"error": "作业不存在"}), 404
        
    if http_job_repository.delete(request_id):
        return jsonify({"message": "作业已删除"})
    else:
        return jsonify({"error": "删除作业失败"}), 500

@http_job_bp.route('/routes', methods=['GET'])
def get_routes():
    """获取所有注册的路由信息
    
    Returns:
        所有路由信息
    """
    routes = {route_id: route.to_dict() for route_id, route in route_registry.get_all_routes().items()}
    return jsonify(routes)

@http_job_bp.route('/nodes', methods=['GET'])
def get_nodes():
    """获取所有工作节点信息
    
    Returns:
        所有节点信息
    """
    nodes = {node_id: node.to_dict() for node_id, node in route_registry.get_all_nodes().items()}
    return jsonify(nodes)

@http_job_bp.route('/nodes/<worker_id>', methods=['GET'])
def get_node(worker_id: str):
    """获取特定工作节点信息
    
    Args:
        worker_id: 工作节点ID
        
    Returns:
        节点信息或错误信息
    """
    node = route_registry.get_node(worker_id)
    
    if node is None:
        return jsonify({"error": "节点不存在"}), 404
        
    return jsonify(node.to_dict())

@http_job_bp.route('/nodes/<worker_id>/status', methods=['PUT'])
def update_node_status(worker_id: str):
    """更新节点状态
    
    Args:
        worker_id: 工作节点ID
        
    Returns:
        成功或错误信息
    """
    try:
        data = request.get_json()
        if not data or 'status' not in data:
            return jsonify({"error": "缺少状态信息"}), 400
            
        status_str = data['status']
        try:
            status = NodeStatus(status_str)
        except ValueError:
            return jsonify({"error": f"无效的状态值: {status_str}"}), 400
            
        success = route_registry.update_node_status(worker_id, status)
        
        if not success:
            return jsonify({"error": "更新节点状态失败"}), 500
            
        return jsonify({"message": f"节点状态更新为 {status.value}"})
        
    except Exception as e:
        current_app.logger.error(f"更新节点状态时发生错误: {e}")
        return jsonify({"error": str(e)}), 500

@http_job_bp.route('/nodes/<worker_id>/heartbeat', methods=['POST'])
def node_heartbeat(worker_id: str):
    """节点心跳更新
    
    Args:
        worker_id: 工作节点ID
        
    Returns:
        成功或错误信息
    """
    success = route_registry.node_heartbeat(worker_id)
    
    if not success:
        return jsonify({"error": "更新节点心跳失败"}), 500
        
    return jsonify({"message": "节点心跳已更新"})

def init_app(app):
    """初始化应用
    
    Args:
        app: Flask应用实例
    """
    app.register_blueprint(http_job_bp) 