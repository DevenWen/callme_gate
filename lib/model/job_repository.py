#!/usr/bin/env python
# -*- coding: utf-8 -*-

from typing import Optional, Dict, List, Type, TypeVar, Generic, Any
import json
from .job import Job
from .http_job import HttpJob
from ..redis_client import RedisClient

# 定义泛型类型变量
T = TypeVar('T', bound=Job)

class JobRepository(Generic[T]):
    """作业仓库，负责作业的存储和检索
    
    使用Redis作为后端存储
    """
    
    def __init__(self, job_type: Type[T], prefix: str = "job"):
        """初始化作业仓库
        
        Args:
            job_type: 作业类型
            prefix: Redis键前缀
        """
        self.job_type = job_type
        self.prefix = prefix
        self.redis = RedisClient()
    
    def _get_key(self, request_id: str) -> str:
        """生成Redis键
        
        Args:
            request_id: 请求ID
            
        Returns:
            完整的Redis键
        """
        return f"{self.prefix}:{request_id}"
    
    def save(self, job: T, expire: Optional[int] = None) -> bool:
        """保存作业到Redis
        
        Args:
            job: 作业实例
            expire: 过期时间（秒）
            
        Returns:
            是否保存成功
        """
        key = self._get_key(job.request_id)
        expire = expire or 60
        return self.redis.set(key, job.to_dict(), expire)
    
    def get(self, request_id: str) -> Optional[T]:
        """通过请求ID获取作业
        
        Args:
            request_id: 请求ID
            
        Returns:
            作业实例，未找到则返回None
        """
        key = self._get_key(request_id)
        data = self.redis.get(key)
        
        if data is None:
            return None
            
        return self.job_type.from_dict(data)
    
    def delete(self, request_id: str) -> bool:
        """删除作业
        
        Args:
            request_id: 请求ID
            
        Returns:
            是否删除成功
        """
        key = self._get_key(request_id)
        return self.redis.delete(key)
    
    def exists(self, request_id: str) -> bool:
        """检查作业是否存在
        
        Args:
            request_id: 请求ID
            
        Returns:
            作业是否存在
        """
        key = self._get_key(request_id)
        return self.redis.exists(key)


# 预定义的常用仓库实例
http_job_repository = JobRepository[HttpJob](HttpJob, "http_job") 