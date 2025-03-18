"""
任务分发类
用于分发任务到对应的工作节点队列
"""
import logging
import json
import time
import uuid
from typing import Dict, List, Any, Optional, Tuple

from ..redis_client import RedisClient
from .route_registry import route_registry
from .route_strategy import RouteStrategy, RouteStrategyFactory

# 配置日志
logger = logging.getLogger("job_dispatcher")

# Redis 键前缀
KEY_PREFIX = "callme_gate#"
# 作业同步队列的 Redis 键前缀
JOB_SYNC_PREFIX = f"{KEY_PREFIX}job_sync"


class JobDispatcher:
    """作业分发器，负责分发HTTP请求到对应的工作队列"""
    
    def __init__(self, default_strategy: str = "round_robin"):
        """初始化作业分发器
        
        Args:
            default_strategy: 默认的路由策略名称
        """
        self.redis = RedisClient()
        self.default_strategy_name = default_strategy
        self.route_strategies: Dict[str, RouteStrategy] = {}  # 路由ID -> 路由策略
        
    def get_strategy(self, route_id: str) -> RouteStrategy:
        """获取路由策略
        
        如果路由没有设置策略，使用默认策略
        
        Args:
            route_id: 路由ID
            
        Returns:
            路由策略对象
        """
        if route_id not in self.route_strategies:
            self.route_strategies[route_id] = RouteStrategyFactory.create_strategy(self.default_strategy_name)
            
        return self.route_strategies[route_id]
        
    def set_route_strategy(self, route_id: str, strategy_name: str, **kwargs) -> bool:
        """设置路由的策略
        
        Args:
            route_id: 路由ID
            strategy_name: 策略名称
            **kwargs: 传递给策略构造函数的参数
            
        Returns:
            是否设置成功
        """
        try:
            self.route_strategies[route_id] = RouteStrategyFactory.create_strategy(strategy_name, **kwargs)
            return True
        except ValueError as e:
            logger.error(f"设置路由策略失败: {e}")
            return False
            
    def reset_route_strategy(self, route_id: str) -> bool:
        """重置路由策略为默认策略
        
        Args:
            route_id: 路由ID
            
        Returns:
            是否重置成功
        """
        if route_id in self.route_strategies:
            del self.route_strategies[route_id]
        return True
        
    def select_worker(self, path: str, method: str, request_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """为请求选择一个合适的工作节点
        
        使用路由策略选择工作节点
        
        Args:
            path: API路径
            method: HTTP方法
            request_data: 请求相关数据
            
        Returns:
            选择的工作节点信息，如果没有可用节点则返回None
        """
        route_id = f"{method.upper()}:{path}"
        
        # 获取路由的所有工作节点
        workers = route_registry.get_route_workers(path, method)
        
        if not workers:
            logger.warning(f"路由 {route_id} 没有可用工作节点")
            return None
            
        # 准备用于路由策略的请求数据
        if request_data is None:
            request_data = {}
        request_data["route_id"] = route_id
        
        # 使用路由策略选择工作节点
        strategy = self.get_strategy(route_id)
        worker = strategy.select_worker(workers, request_data)
        
        if worker:
            logger.info(f"为路由 {route_id} 选择工作节点 {worker.get('worker_id')}")
        else:
            logger.warning(f"路由策略无法为 {route_id} 选择工作节点")
            
        return worker
        
    def get_sync_key(self, request_id: str) -> str:
        """获取请求同步键名
        
        Args:
            request_id: 请求ID
            
        Returns:
            同步键名
        """
        return f"{JOB_SYNC_PREFIX}:{request_id}"
        
    def dispatch_job(self, request_id: str, path: str, method: str, data: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """分发作业到对应的工作队列
        
        Args:
            request_id: 请求ID
            path: API路径
            method: HTTP方法
            data: 额外的请求数据，用于路由决策
            
        Returns:
            (是否成功分发, 选择的工作节点信息)
        """
        # 选择工作节点
        worker = self.select_worker(path, method, data)
        if not worker:
            logger.error(f"无法找到处理 {method} {path} 的工作节点")
            return False, None
            
        # 获取工作节点队列
        queue = worker.get("queue")
        
        # 获取同步键名并创建（用于后续阻塞获取结果）
        sync_key = self.get_sync_key(request_id)
        self.redis.client.delete(sync_key)
        
        try:
            # 添加作业到队列
            self.redis.client.rpush(queue, request_id)
            logger.info(f"作业 {request_id} 已分发到队列 {queue}")
            return True, worker
        except Exception as e:
            logger.error(f"分发作业 {request_id} 时发生错误: {e}")
            return False, worker
            
    def wait_for_result(self, request_id: str, timeout: int = 5) -> Optional[str]:
        """等待作业处理结果
        
        使用阻塞方式等待结果
        
        Args:
            request_id: 请求ID
            timeout: 超时时间(秒)
            
        Returns:
            处理结果的JSON字符串，超时返回None
        """
        sync_key = self.get_sync_key(request_id)
        
        try:
            # 使用阻塞方式获取结果
            result = self.redis.client.blpop(sync_key, timeout)
            if result:
                _, value = result
                logger.info(f"收到作业 {request_id} 的处理结果")
                return value
            else:
                logger.warning(f"等待作业 {request_id} 结果超时")
                return None
        except Exception as e:
            logger.error(f"等待作业 {request_id} 结果时发生错误: {e}")
            return None
            
    def publish_result(self, request_id: str, result: str) -> bool:
        """发布作业处理结果
        
        Args:
            request_id: 请求ID
            result: 处理结果的JSON字符串
            
        Returns:
            是否成功发布
        """
        sync_key = self.get_sync_key(request_id)
        
        try:
            # 添加结果到同步列表
            self.redis.client.rpush(sync_key, result)
            # 设置过期时间，防止无人消费的结果长期占用内存
            self.redis.client.expire(sync_key, 60)
            logger.info(f"已发布作业 {request_id} 的处理结果")
            return True
        except Exception as e:
            logger.error(f"发布作业 {request_id} 结果时发生错误: {e}")
            return False
            
    def generate_request_id(self) -> str:
        """生成唯一的请求ID
        
        Returns:
            请求ID
        """
        return str(uuid.uuid4())


# 单例实例
job_dispatcher = JobDispatcher() 