"""
路由策略抽象类和实现
用于根据不同策略选择工作节点
"""
from typing import Dict, List, Any, Optional, Protocol
from abc import ABC, abstractmethod
import random
import time

from .node import Node


class RouteStrategy(ABC):
    """路由策略抽象基类"""
    
    @abstractmethod
    def select_worker(self, workers: List[Dict[str, Any]], request_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """根据策略从工作节点列表中选择一个节点
        
        Args:
            workers: 可用工作节点列表
            request_data: 请求相关数据，可用于上下文相关的路由决策
            
        Returns:
            选中的工作节点，如果没有可用节点则返回None
        """
        pass


class RandomStrategy(RouteStrategy):
    """随机选择策略
    
    从可用节点中随机选择一个
    """
    
    def select_worker(self, workers: List[Dict[str, Any]], request_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """随机选择一个工作节点
        
        Args:
            workers: 可用工作节点列表
            request_data: 请求相关数据（此策略中未使用）
            
        Returns:
            随机选择的工作节点，如果没有可用节点则返回None
        """
        if not workers:
            return None
            
        return random.choice(workers)


class RoundRobinStrategy(RouteStrategy):
    """轮询策略
    
    按顺序循环选择节点
    """
    
    def __init__(self):
        """初始化轮询策略"""
        self.last_index: Dict[str, int] = {}  # 路由ID -> 上次选择的索引
        
    def select_worker(self, workers: List[Dict[str, Any]], request_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """轮询选择一个工作节点
        
        Args:
            workers: 可用工作节点列表
            request_data: 请求相关数据，需要包含route_id字段
            
        Returns:
            按轮询方式选择的工作节点，如果没有可用节点则返回None
        """
        if not workers:
            return None
            
        route_id = request_data.get("route_id") if request_data else "default"
        
        # 获取上次选择的索引，默认为-1
        last_idx = self.last_index.get(route_id, -1)
        
        # 计算下一个索引
        next_idx = (last_idx + 1) % len(workers)
        
        # 更新索引
        self.last_index[route_id] = next_idx
        
        return workers[next_idx]


class LeastConnectionStrategy(RouteStrategy):
    """最少连接策略
    
    选择当前处理请求最少的节点
    """
    
    def select_worker(self, workers: List[Dict[str, Any]], request_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """选择当前负载最低的工作节点
        
        Args:
            workers: 可用工作节点列表
            request_data: 请求相关数据（此策略中未使用）
            
        Returns:
            负载最低的工作节点，如果没有可用节点则返回None
        """
        if not workers:
            return None
            
        # 按照总请求数与完成请求数的差值排序，差值最小的负载最低
        sorted_workers = sorted(
            workers,
            key=lambda w: w.get("metrics", {}).get("total_requests", 0) - w.get("metrics", {}).get("completed_requests", 0)
        )
        
        return sorted_workers[0]


class WeightedResponseTimeStrategy(RouteStrategy):
    """加权响应时间策略
    
    根据节点的平均响应时间加权选择，响应更快的节点被选中概率更高
    """
    
    def select_worker(self, workers: List[Dict[str, Any]], request_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """基于响应时间加权选择工作节点
        
        Args:
            workers: 可用工作节点列表
            request_data: 请求相关数据（此策略中未使用）
            
        Returns:
            选择的工作节点，如果没有可用节点则返回None
        """
        if not workers:
            return None
            
        # 计算每个节点的权重（1/avg_process_time）
        # 平均处理时间越短，权重越大
        weighted_workers = []
        total_weight = 0.0
        
        for worker in workers:
            # 从指标中获取平均处理时间，默认为100ms
            avg_time = worker.get("metrics", {}).get("avg_process_time", 100)
            
            # 避免除以0，最小为1ms
            avg_time = max(avg_time, 1)
            
            # 计算权重：处理时间的倒数
            weight = 1.0 / avg_time
            total_weight += weight
            
            weighted_workers.append((worker, weight))
            
        # 如果没有有效权重，回退到随机选择
        if total_weight <= 0:
            return random.choice(workers)
            
        # 基于权重随机选择
        r = random.uniform(0, total_weight)
        upto = 0
        
        for worker, weight in weighted_workers:
            upto += weight
            if upto >= r:
                return worker
                
        # 保险起见，返回最后一个
        return weighted_workers[-1][0]


class SpecificVersionStrategy(RouteStrategy):
    """特定版本策略
    
    选择实现特定版本的节点
    """
    
    def __init__(self, preferred_version: str):
        """初始化特定版本策略
        
        Args:
            preferred_version: 优先选择的版本
        """
        self.preferred_version = preferred_version
        
    def select_worker(self, workers: List[Dict[str, Any]], request_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """选择特定版本的工作节点
        
        Args:
            workers: 可用工作节点列表
            request_data: 请求相关数据（此策略中未使用）
            
        Returns:
            实现特定版本的工作节点，如果没有可用节点则返回None
        """
        if not workers:
            return None
            
        # 从请求中获取目标版本，如果没有则使用构造函数中的版本
        target_version = (request_data.get("version") if request_data else None) or self.preferred_version
        
        # 筛选出实现目标版本的节点
        matching_workers = [w for w in workers if w.get("version") == target_version]
        
        # 如果没有实现目标版本的节点，返回None
        if not matching_workers:
            return None
            
        # 从匹配的节点中随机选择一个
        return random.choice(matching_workers)


# 创建路由策略工厂
class RouteStrategyFactory:
    """路由策略工厂，用于创建各种路由策略"""
    
    @staticmethod
    def create_strategy(strategy_name: str, **kwargs) -> RouteStrategy:
        """创建指定名称的路由策略
        
        Args:
            strategy_name: 策略名称
            **kwargs: 传递给策略构造函数的参数
            
        Returns:
            路由策略实例
            
        Raises:
            ValueError: 如果策略名称无效
        """
        strategy_map = {
            "random": RandomStrategy,
            "round_robin": RoundRobinStrategy,
            "least_connection": LeastConnectionStrategy,
            "weighted_response_time": WeightedResponseTimeStrategy,
            "specific_version": SpecificVersionStrategy
        }
        
        if strategy_name not in strategy_map:
            raise ValueError(f"未知的路由策略: {strategy_name}")
            
        strategy_class = strategy_map[strategy_name]
        return strategy_class(**kwargs) 