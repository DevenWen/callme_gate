#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Redis分布式锁实现
提供基于Redis的分布式锁功能和装饰器
"""
import time
import uuid
import logging
import functools
from typing import Optional, Union, Callable, Any, TypeVar, cast

from ..redis_client import RedisClient

# 配置日志
logger = logging.getLogger(__name__)

# 锁键前缀
LOCK_KEY_PREFIX = "redis_lock"

# 函数返回类型
T = TypeVar('T')


class RedisLock:
    """Redis分布式锁实现
    
    基于Redis的SET命令和过期时间实现分布式锁
    """
    
    def __init__(
        self, 
        lock_name: str, 
        expire_seconds: int = 30, 
        retry_times: int = 0,
        retry_delay: float = 0.2
    ):
        """初始化分布式锁
        
        Args:
            lock_name: 锁名称，用于标识要锁定的资源
            expire_seconds: 锁的过期时间（秒）
            retry_times: 获取锁失败时的重试次数
            retry_delay: 重试间隔（秒）
        """
        self.lock_name = lock_name
        self.lock_key = f"{LOCK_KEY_PREFIX}:{lock_name}"
        self.expire_seconds = expire_seconds
        self.retry_times = retry_times
        self.retry_delay = retry_delay
        self.lock_id = str(uuid.uuid4())  # 唯一锁标识符
        self.redis = RedisClient()
        self.redis_client = self.redis.client  # 直接暴露Redis客户端，方便测试访问
        self.acquired = False
    
    def acquire(self) -> bool:
        """获取锁
        
        使用Redis SET命令和NX选项尝试获取锁
        如果设置失败，根据配置进行重试
        
        Returns:
            是否成功获取锁
        """
        # 尝试获取锁
        for i in range(self.retry_times + 1):
            # 使用 SET NX 命令实现分布式锁
            # 只有当键不存在时才设置值，保证原子性
            success = self.redis.client.set(
                self.lock_key, 
                self.lock_id, 
                nx=True,
                ex=self.expire_seconds
            )
            
            if success:
                logger.debug(f"成功获取锁: {self.lock_name} (ID: {self.lock_id})")
                self.acquired = True
                return True
            
            if i < self.retry_times:
                logger.debug(f"获取锁失败，重试 ({i+1}/{self.retry_times}): {self.lock_name}")
                time.sleep(self.retry_delay)
        
        logger.debug(f"获取锁最终失败: {self.lock_name}")
        return False
    
    def release(self) -> bool:
        """释放锁
        
        只有锁的拥有者（持有相同lock_id的客户端）才能释放锁
        
        Returns:
            是否成功释放锁
        """
        # 获取当前锁的值
        current_lock_value = self.redis.client.get(self.lock_key)
        
        # 检查是否是锁的拥有者
        if current_lock_value != self.lock_id:
            logger.warning(f"无法释放锁: {self.lock_name}，不是锁的拥有者")
            return False
        
        # 删除锁
        success = self.redis.client.delete(self.lock_key)
        if success:
            logger.debug(f"成功释放锁: {self.lock_name} (ID: {self.lock_id})")
            self.acquired = False
        else:
            logger.warning(f"释放锁失败: {self.lock_name} (ID: {self.lock_id})")
            
        return bool(success)
    
    def extend(self, additional_seconds: int) -> bool:
        """延长锁的过期时间
        
        Args:
            additional_seconds: 要增加的秒数
            
        Returns:
            是否成功延长锁时间
        """
        # 获取当前锁的值和剩余时间
        current_lock_value = self.redis.client.get(self.lock_key)
        
        # 检查是否是锁的拥有者
        if current_lock_value != self.lock_id:
            logger.warning(f"无法延长锁: {self.lock_name}，不是锁的拥有者")
            return False
            
        # 获取剩余时间
        remaining_time = self.redis.client.ttl(self.lock_key)
        if remaining_time < 0:
            # 锁已过期或不存在
            logger.warning(f"锁已过期或不存在: {self.lock_name}")
            return False
            
        # 设置新的过期时间
        new_expire = remaining_time + additional_seconds
        success = self.redis.client.set(
            self.lock_key, 
            self.lock_id, 
            ex=new_expire
        )
        
        if success:
            logger.debug(f"成功延长锁: {self.lock_name}，新过期时间: {new_expire}秒")
        else:
            logger.warning(f"延长锁失败: {self.lock_name}")
            
        return bool(success)
    
    def is_alive(self) -> bool:
        """检查锁是否仍然有效
        
        Returns:
            锁是否仍然有效
        """
        current_lock_value = self.redis.client.get(self.lock_key)
        return current_lock_value == self.lock_id
    
    def __enter__(self) -> 'RedisLock':
        """上下文管理器入口"""
        self.acquire()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器退出"""
        if self.acquired:
            self.release()


def with_distributed_lock(
    lock_name_or_func: Union[str, Callable],
    expire_seconds: int = 30,
    retry_times: int = 0,
    retry_delay: float = 0.2
) -> Callable:
    """分布式锁装饰器
    
    为函数添加分布式锁，避免并发执行
    
    Args:
        lock_name_or_func: 锁名称或返回锁名称的函数
        expire_seconds: 锁的过期时间（秒）
        retry_times: 获取锁失败时的重试次数
        retry_delay: 重试间隔（秒）
        
    Returns:
        装饰器函数
    """
    # 检查是否直接使用装饰器
    if callable(lock_name_or_func) and not isinstance(lock_name_or_func, str):
        # 这种情况是直接使用 @with_distributed_lock 而不带参数
        # 将被装饰函数作为锁名称
        func = lock_name_or_func
        lock_name = func.__name__  # 使用函数名作为锁名称
        
        # 直接创建并返回包装函数
        @functools.wraps(func)
        def direct_wrapper(*args: Any, **kwargs: Any) -> T:
            lock = RedisLock(
                lock_name=lock_name,
                expire_seconds=expire_seconds,
                retry_times=retry_times,
                retry_delay=retry_delay
            )
            
            acquired = lock.acquire()
            if not acquired:
                logger.warning(f"无法获取锁: {lock_name}，跳过执行 {func.__name__}")
                return None
            
            try:
                return func(*args, **kwargs)
            finally:
                lock.release()
                
        return direct_wrapper
    
    # 处理传递了参数的情况
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        """实际的装饰器"""
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # 获取锁名称
            if callable(lock_name_or_func) and not isinstance(lock_name_or_func, str):
                # 如果是可调用对象，调用它生成锁名称
                lock_name = lock_name_or_func(*args, **kwargs)
            else:
                # 否则直接使用它作为锁名称
                lock_name = str(lock_name_or_func)
            
            # 创建锁
            lock = RedisLock(
                lock_name=lock_name,
                expire_seconds=expire_seconds,
                retry_times=retry_times,
                retry_delay=retry_delay
            )
            
            # 尝试获取锁
            acquired = lock.acquire()
            if not acquired:
                logger.warning(f"无法获取锁: {lock_name}，跳过执行 {func.__name__}")
                return None  # 无法获取锁，返回None
            
            try:
                # 执行被装饰的函数
                return func(*args, **kwargs)
            finally:
                # 释放锁
                lock.release()
                
        return wrapper
    
    return decorator 