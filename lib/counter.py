from typing import Dict, Any, Optional
from .redis_client import RedisClient

class Counter:
    """计数器类
    
    使用Redis存储计数器的值
    """
    
    def __init__(self, key_prefix: str = "counter"):
        """初始化计数器
        
        Args:
            key_prefix: Redis键前缀
        """
        self.redis = RedisClient()
        self.key_prefix = key_prefix
        
    def _get_key(self, counter_name: str) -> str:
        """获取计数器键
        
        Args:
            counter_name: 计数器名称
            
        Returns:
            Redis键
        """
        return f"{self.key_prefix}:{counter_name}"
        
    def get(self, name: str, default: int = 0) -> int:
        """获取计数器值
        
        Args:
            name: 计数器名称
            default: 默认值
            
        Returns:
            计数器的当前值
        """
        key = self._get_key(name)
        value = self.redis.get(key)
        
        if value is None:
            return default
            
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
            
    def set(self, name: str, value: int) -> bool:
        """设置计数器值
        
        Args:
            name: 计数器名称
            value: 计数器值
            
        Returns:
            是否设置成功
        """
        key = self._get_key(name)
        return self.redis.set(key, value)
        
    def increment(self, name: str, amount: int = 1) -> int:
        """增加计数器值
        
        Args:
            name: 计数器名称
            amount: 增加量
            
        Returns:
            增加后的计数器值
        """
        key = self._get_key(name)
        try:
            # 使用Redis的INCRBY命令原子性地增加计数器值
            new_value = self.redis.client.incrby(key, amount)
            return new_value
        except Exception as e:
            print(f"计数器增加失败: {e}")
            # 失败时，尝试使用非原子性操作
            current = self.get(name, 0)
            new_value = current + amount
            self.set(name, new_value)
            return new_value
            
    def decrement(self, name: str, amount: int = 1) -> int:
        """减少计数器值
        
        Args:
            name: 计数器名称
            amount: 减少量
            
        Returns:
            减少后的计数器值
        """
        return self.increment(name, -amount)
        
    def reset(self, name: str) -> bool:
        """重置计数器
        
        Args:
            name: 计数器名称
            
        Returns:
            是否重置成功
        """
        return self.set(name, 0)
        
    def delete(self, name: str) -> bool:
        """删除计数器
        
        Args:
            name: 计数器名称
            
        Returns:
            是否删除成功
        """
        key = self._get_key(name)
        return self.redis.delete(key)
        
# 全局计数器实例
counter = Counter() 