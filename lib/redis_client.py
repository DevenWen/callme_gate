#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import redis
import logging

logger = logging.getLogger("redic_client")

class RedisClient:
    """Redis客户端类，用于与Redis服务器交互"""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化Redis连接"""
        if self._initialized:
            return
            
        host = os.getenv('REDIS_HOST', 'localhost')
        port = int(os.getenv('REDIS_PORT', 6379))
        db = int(os.getenv('REDIS_DB', 0))
        password = os.getenv('REDIS_PASSWORD', '')
        use_ssl = os.getenv('REDIS_USE_SSL', 'false').lower() == 'true'

        logger.info(f"Redis连接配置: host={host}, port={port}, db={db}, use_ssl={use_ssl}")
        
        # 修正密码处理方式，只有当密码不为空字符串时才传递
        connection_params = {
            'host': host,
            'port': port,
            'db': db,
            'ssl': use_ssl,
            'decode_responses': True  # 自动将响应解码为字符串
        }
        
        if password:
            connection_params['password'] = password
            logger.info("使用密码认证连接Redis")
        else:
            logger.warning("未提供Redis密码，可能无法连接需要认证的Redis服务器")
        
        try:
            self.client = redis.Redis(**connection_params)
            # 测试连接
            self.client.ping()
            logger.info("成功连接到Redis服务器")
        except redis.exceptions.AuthenticationError as e:
            logger.error(f"Redis认证失败: {str(e)}")
            raise
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Redis连接错误: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"初始化Redis客户端时发生错误: {str(e)}")
            raise
            
        self._initialized = True
        
    def set(self, key, value, expire=None):
        """存储键值对到Redis
        
        Args:
            key (str): 键
            value (any): 值(会被转为JSON字符串)
            expire (int, optional): 过期时间(秒)
        
        Returns:
            bool: 操作是否成功
        """
        try:
            # 如果值不是字符串，转换为JSON
            if not isinstance(value, str):
                value = json.dumps(value)
            
            self.client.set(key, value)
            if expire:
                self.client.expire(key, expire)
            return True
        except Exception as e:
            logger.error(f"Redis set error: {str(e)}")
            return False
    
    def get(self, key, default=None):
        """从Redis获取值
        
        Args:
            key (str): 键
            default (any, optional): 默认值
        
        Returns:
            any: 获取的值或默认值
        """
        try:
            value = self.client.get(key)
            if value is None:
                return default
            
            # 尝试解析JSON，如果失败则返回原始字符串
            try:
                return json.loads(value)
            except (TypeError, json.JSONDecodeError):
                return value
        except Exception as e:
            logger.error(f"Redis get error: {str(e)}")
            return default
    
    def delete(self, key):
        """删除键值对
        
        Args:
            key (str): 键
        
        Returns:
            bool: 操作是否成功
        """
        try:
            return bool(self.client.delete(key))
        except Exception as e:
            logger.error(f"Redis delete error: {str(e)}")
            return False
    
    def exists(self, key):
        """检查键是否存在
        
        Args:
            key (str): 键
        
        Returns:
            bool: 键是否存在
        """
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            logger.error(f"Redis exists error: {str(e)}")
            return False
            
    def ttl(self, key):
        """获取键的剩余生存时间
        
        Args:
            key (str): 键
        
        Returns:
            int: 剩余秒数，-1表示永久，-2表示不存在
        """
        try:
            return self.client.ttl(key)
        except Exception as e:
            logger.error(f"Redis ttl error: {str(e)}")
            return -2 