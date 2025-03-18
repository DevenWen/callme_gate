"""
路由注册类
用于管理路由信息和路由注册
"""
import logging
import json
import time
from typing import Dict, List, Any, Optional, Set, Tuple

from ..redis_client import RedisClient
from .route import Route
from .node import Node, NodeStatus

# 配置日志
logger = logging.getLogger("route_registry")

# Redis 键前缀
KEY_PREFIX = "callme_gate#"
# 路由注册信息的 Redis 键
ROUTES_KEY = f"{KEY_PREFIX}routes"
# 节点信息的 Redis 键
NODES_KEY = f"{KEY_PREFIX}nodes"
# 路由节点映射的 Redis 键
ROUTE_NODES_PREFIX = f"{KEY_PREFIX}route_nodes"
# 节点路由映射的 Redis 键
NODE_ROUTES_PREFIX = f"{KEY_PREFIX}node_routes"


class RouteRegistry:
    """路由注册表，管理API路由和工作节点的映射关系"""
    
    def __init__(self):
        """初始化路由注册表"""
        self.redis = RedisClient()
        
    def get_route(self, path: str, method: str) -> Optional[Route]:
        """获取路由信息
        
        Args:
            path: API路径
            method: HTTP方法
            
        Returns:
            路由对象，如果不存在则返回None
        """
        route_id = f"{method.upper()}:{path}"
        routes = self.redis.get(ROUTES_KEY, {})
        
        if route_id not in routes:
            return None
            
        return Route.from_dict(routes[route_id])
        
    def get_all_routes(self) -> Dict[str, Route]:
        """获取所有路由信息
        
        Returns:
            路由ID到路由对象的映射
        """
        routes_dict = self.redis.get(ROUTES_KEY, {})
        return {route_id: Route.from_dict(route_data) for route_id, route_data in routes_dict.items()}
        
    def save_route(self, route: Route) -> bool:
        """保存路由信息
        
        Args:
            route: 路由对象
            
        Returns:
            是否保存成功
        """
        routes = self.redis.get(ROUTES_KEY, {})
        routes[route.route_id] = route.to_dict()
        
        return self.redis.set(ROUTES_KEY, routes)
        
    def delete_route(self, route_id: str) -> bool:
        """删除路由信息
        
        Args:
            route_id: 路由ID
            
        Returns:
            是否删除成功
        """
        routes = self.redis.get(ROUTES_KEY, {})
        
        if route_id not in routes:
            return False
            
        del routes[route_id]
        return self.redis.set(ROUTES_KEY, routes)
        
    def register_route(self, path: str, method: str, worker_id: str, version: str, queue: str, timeout: int = 5, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """注册路由和工作节点的映射关系
        
        Args:
            path: API路径
            method: HTTP方法
            worker_id: 工作节点唯一标识
            version: 服务版本
            queue: 工作节点的队列名称
            timeout: 处理超时时间（秒）
            metadata: 额外的元数据
            
        Returns:
            是否注册成功
        """
        logger.info(f"注册路由: {method} {path} 到节点 {worker_id} (版本: {version}, 队列: {queue}, 超时: {timeout}秒)")
        
        try:
            # 获取或创建路由
            route = self.get_route(path, method)
            if not route:
                route = Route(path, method, timeout)
                
            # 添加工作节点到路由
            route.add_worker(worker_id, version, queue, metadata)
            
            # 保存路由信息
            if not self.save_route(route):
                logger.error(f"无法保存路由信息: {route.route_id}")
                return False
                
            # 获取节点信息
            node = self.get_node(worker_id)
            if not node:
                # 如果节点不存在，创建新节点
                node = Node(worker_id, version, queue)
                node.update_status(NodeStatus.ONLINE)
                
            # 添加路由到节点
            node.add_route(route.route_id)
            
            # 保存节点信息
            if not self.save_node(node):
                logger.error(f"无法保存节点信息: {worker_id}")
                return False
                
            # 更新路由-节点映射集合
            route_nodes_key = f"{ROUTE_NODES_PREFIX}:{route.route_id}"
            self.redis.client.sadd(route_nodes_key, worker_id)
            
            # 更新节点-路由映射集合
            node_routes_key = f"{NODE_ROUTES_PREFIX}:{worker_id}"
            self.redis.client.sadd(node_routes_key, route.route_id)
            
            logger.info(f"路由 {route.route_id} 注册到节点 {worker_id} 成功")
            return True
            
        except Exception as e:
            logger.error(f"注册路由时发生错误: {e}")
            return False
            
    def unregister_route(self, path: str, method: str, worker_id: str) -> bool:
        """取消注册路由和工作节点的映射关系
        
        Args:
            path: API路径
            method: HTTP方法
            worker_id: 工作节点唯一标识
            
        Returns:
            是否取消注册成功
        """
        logger.info(f"取消注册路由: {method} {path} 从节点 {worker_id}")
        
        try:
            route_id = f"{method.upper()}:{path}"
            
            # 获取路由信息
            route = self.get_route(path, method)
            if not route:
                logger.warning(f"路由不存在: {route_id}")
                return False
                
            # 从路由中移除工作节点
            if not route.remove_worker(worker_id):
                logger.warning(f"节点 {worker_id} 不在路由 {route_id} 中")
                return False
                
            # 保存路由信息（如果没有工作节点，删除路由）
            if route.get_workers():
                if not self.save_route(route):
                    logger.error(f"无法保存路由信息: {route_id}")
                    return False
            else:
                if not self.delete_route(route_id):
                    logger.error(f"无法删除路由信息: {route_id}")
                    return False
                    
            # 获取节点信息
            node = self.get_node(worker_id)
            if not node:
                logger.warning(f"节点不存在: {worker_id}")
                return True  # 返回成功，因为我们已经从路由中移除了节点
                
            # 从节点中移除路由
            node.remove_route(route_id)
            
            # 保存节点信息
            if not self.save_node(node):
                logger.error(f"无法保存节点信息: {worker_id}")
                return False
                
            # 更新路由-节点映射集合
            route_nodes_key = f"{ROUTE_NODES_PREFIX}:{route_id}"
            self.redis.client.srem(route_nodes_key, worker_id)
            
            # 更新节点-路由映射集合
            node_routes_key = f"{NODE_ROUTES_PREFIX}:{worker_id}"
            self.redis.client.srem(node_routes_key, route_id)
            
            logger.info(f"路由 {route_id} 从节点 {worker_id} 取消注册成功")
            return True
            
        except Exception as e:
            logger.error(f"取消注册路由时发生错误: {e}")
            return False
            
    def get_node(self, worker_id: str) -> Optional[Node]:
        """获取节点信息
        
        Args:
            worker_id: 节点ID
            
        Returns:
            节点对象，如果不存在则返回None
        """
        nodes = self.redis.get(NODES_KEY, {})
        
        if worker_id not in nodes:
            return None
            
        return Node.from_dict(nodes[worker_id])
        
    def get_all_nodes(self) -> Dict[str, Node]:
        """获取所有节点信息
        
        Returns:
            节点ID到节点对象的映射
        """
        nodes_dict = self.redis.get(NODES_KEY, {})
        return {node_id: Node.from_dict(node_data) for node_id, node_data in nodes_dict.items()}
        
    def save_node(self, node: Node) -> bool:
        """保存节点信息
        
        Args:
            node: 节点对象
            
        Returns:
            是否保存成功
        """
        nodes = self.redis.get(NODES_KEY, {})
        nodes[node.worker_id] = node.to_dict()
        
        return self.redis.set(NODES_KEY, nodes)
        
    def delete_node(self, worker_id: str) -> bool:
        """删除节点信息
        
        Args:
            worker_id: 节点ID
            
        Returns:
            是否删除成功
        """
        nodes = self.redis.get(NODES_KEY, {})
        
        if worker_id not in nodes:
            return False
            
        del nodes[worker_id]
        return self.redis.set(NODES_KEY, nodes)
        
    def register_node(self, worker_id: str, version: str, queue: str, status: NodeStatus = NodeStatus.ONLINE, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """注册工作节点
        
        Args:
            worker_id: 工作节点唯一标识
            version: 服务版本
            queue: 队列名称
            status: 节点状态
            metadata: 额外的元数据
            
        Returns:
            是否注册成功
        """
        logger.info(f"注册节点: {worker_id} (版本: {version}, 队列: {queue}, 状态: {status.value})")
        
        try:
            # 获取或创建节点
            node = self.get_node(worker_id)
            if not node:
                node = Node(worker_id, version, queue)
            else:
                # 更新现有节点信息
                node.version = version
                node.queue = queue
                
            # 更新节点状态和元数据
            node.update_status(status)
            if metadata:
                node.metadata.update(metadata)
                
            # 保存节点信息
            if not self.save_node(node):
                logger.error(f"无法保存节点信息: {worker_id}")
                return False
                
            logger.info(f"节点 {worker_id} 注册成功")
            return True
            
        except Exception as e:
            logger.error(f"注册节点时发生错误: {e}")
            return False
            
    def unregister_node(self, worker_id: str) -> bool:
        """取消注册工作节点
        
        同时取消该节点关联的所有路由
        
        Args:
            worker_id: 工作节点唯一标识
            
        Returns:
            是否取消注册成功
        """
        logger.info(f"取消注册节点: {worker_id}")
        
        try:
            # 获取节点信息
            node = self.get_node(worker_id)
            if not node:
                logger.warning(f"节点不存在: {worker_id}")
                return False
                
            # 获取节点关联的所有路由
            node_routes_key = f"{NODE_ROUTES_PREFIX}:{worker_id}"
            route_ids = self.redis.client.smembers(node_routes_key)
            
            # 从每个路由中移除该节点
            for route_id in route_ids:
                parts = route_id.split(":", 1)
                if len(parts) == 2:
                    method, path = parts
                    # 使用路由对象操作而不是直接修改Redis
                    self.unregister_route(path, method, worker_id)
                    
            # 删除节点-路由映射集合
            self.redis.client.delete(node_routes_key)
            
            # 将节点状态设置为离线
            node.update_status(NodeStatus.OFFLINE)
            self.save_node(node)
            
            logger.info(f"节点 {worker_id} 取消注册成功")
            return True
            
        except Exception as e:
            logger.error(f"取消注册节点时发生错误: {e}")
            return False
            
    def update_node_status(self, worker_id: str, status: NodeStatus) -> bool:
        """更新节点状态
        
        Args:
            worker_id: 工作节点唯一标识
            status: 新的节点状态
            
        Returns:
            是否更新成功
        """
        logger.info(f"更新节点状态: {worker_id} -> {status.value}")
        
        try:
            # 获取节点信息
            node = self.get_node(worker_id)
            if not node:
                logger.warning(f"节点不存在: {worker_id}")
                return False
                
            # 更新节点状态
            node.update_status(status)
            
            # 保存节点信息
            if not self.save_node(node):
                logger.error(f"无法保存节点信息: {worker_id}")
                return False
                
            logger.info(f"节点 {worker_id} 状态更新为 {status.value}")
            return True
            
        except Exception as e:
            logger.error(f"更新节点状态时发生错误: {e}")
            return False
            
    def node_heartbeat(self, worker_id: str) -> bool:
        """更新节点心跳
        
        Args:
            worker_id: 工作节点唯一标识
            
        Returns:
            是否更新成功
        """
        try:
            # 获取节点信息
            node = self.get_node(worker_id)
            if not node:
                logger.warning(f"节点不存在: {worker_id}")
                return False
                
            # 更新心跳时间
            node.heartbeat()
            
            # 如果节点不是在线状态，设置为在线
            if node.status != NodeStatus.ONLINE:
                node.update_status(NodeStatus.ONLINE)
                
            # 保存节点信息
            if not self.save_node(node):
                logger.error(f"无法保存节点信息: {worker_id}")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"更新节点心跳时发生错误: {e}")
            return False
            
    def get_route_timeout(self, path: str, method: str) -> int:
        """获取路由的超时设置
        
        Args:
            path: API路径
            method: HTTP方法
            
        Returns:
            路由的超时时间(秒)，默认为5秒
        """
        route = self.get_route(path, method)
        return route.timeout if route else 5
        
    def get_route_workers(self, path: str, method: str) -> List[Dict[str, Any]]:
        """获取路由的所有工作节点
        
        Args:
            path: API路径
            method: HTTP方法
            
        Returns:
            工作节点信息列表
        """
        route = self.get_route(path, method)
        if not route:
            return []
            
        return route.get_workers()
        
    def clean_inactive_nodes(self, max_heartbeat_age: int = 60) -> int:
        """清理不活跃的节点
        
        Args:
            max_heartbeat_age: 最大心跳间隔（秒）
            
        Returns:
            清理的节点数量
        """
        logger.info(f"开始清理不活跃节点 (最大心跳间隔: {max_heartbeat_age}秒)")
        
        try:
            # 获取所有节点
            nodes = self.get_all_nodes()
            cleaned_count = 0
            
            # 筛选出不活跃的节点
            for worker_id, node in nodes.items():
                if not node.is_alive(max_heartbeat_age):
                    logger.info(f"节点 {worker_id} 不活跃，最后心跳: {int(time.time()) - node.last_heartbeat}秒前")
                    
                    # 将节点状态设置为离线
                    node.update_status(NodeStatus.OFFLINE)
                    self.save_node(node)
                    
                    cleaned_count += 1
                    
            logger.info(f"清理完成，共 {cleaned_count} 个不活跃节点")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"清理不活跃节点时发生错误: {e}")
            return 0


# 单例实例
route_registry = RouteRegistry() 