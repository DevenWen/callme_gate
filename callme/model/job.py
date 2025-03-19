#!/usr/bin/env python
# -*- coding: utf-8 -*-

import uuid
import json
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, ClassVar

class JobStatus(str, Enum):
    """作业状态枚举类"""
    PENDING = "pending"     # 等待执行
    RUNNING = "running"     # 正在执行
    COMPLETED = "completed" # 已完成
    FAILED = "failed"       # 执行失败
    CANCELLED = "cancelled" # 已取消

class Job:
    """基础作业类
    
    包含所有作业通用的属性和方法
    """
    
    # 类属性，定义属性的序列化映射
    serializable_fields: ClassVar[Dict[str, str]] = {
        "request_id": "request_id",
        "status": "status",
        "create_time": "create_time",
        "update_time": "update_time"
    }
    
    def __init__(
        self,
        request_id: Optional[str] = None,
        status: JobStatus = JobStatus.PENDING,
        create_time: Optional[datetime] = None,
        update_time: Optional[datetime] = None
    ):
        """初始化作业
        
        Args:
            request_id: 请求ID，如不提供则自动生成
            status: 作业状态，默认为PENDING
            create_time: 创建时间，如不提供则使用当前时间
            update_time: 更新时间，如不提供则使用当前时间
        """
        self.request_id = request_id or str(uuid.uuid4())
        self.status = status if isinstance(status, JobStatus) else JobStatus(status)
        self.create_time = create_time or datetime.now()
        self.update_time = update_time or self.create_time
    
    def update_status(self, status: JobStatus) -> None:
        """更新作业状态
        
        Args:
            status: 新的作业状态
        """
        self.status = status if isinstance(status, JobStatus) else JobStatus(status)
        self.update_time = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """将作业转换为字典
        
        Returns:
            作业属性的字典表示
        """
        result = {}
        
        for attr_name, dict_key in self.serializable_fields.items():
            value = getattr(self, attr_name)
            
            # 处理特殊类型
            if isinstance(value, datetime):
                value = value.isoformat()
            elif isinstance(value, Enum):
                value = value.value
                
            result[dict_key] = value
            
        return result
    
    def to_json(self) -> str:
        """将作业转换为JSON字符串
        
        Returns:
            作业的JSON字符串表示
        """
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Job':
        """从字典创建作业实例
        
        Args:
            data: 包含作业属性的字典
            
        Returns:
            创建的作业实例
        """
        # 反向映射字典键名到属性名
        reverse_mapping = {v: k for k, v in cls.serializable_fields.items()}
        kwargs = {}
        
        for dict_key, value in data.items():
            if dict_key in reverse_mapping:
                attr_name = reverse_mapping[dict_key]
                
                # 处理特殊类型
                if attr_name == 'create_time' or attr_name == 'update_time':
                    if value:
                        value = datetime.fromisoformat(value)
                elif attr_name == 'status':
                    value = JobStatus(value)
                    
                kwargs[attr_name] = value
                
        return cls(**kwargs)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Job':
        """从JSON字符串创建作业实例
        
        Args:
            json_str: 作业的JSON字符串表示
            
        Returns:
            创建的作业实例
        """
        return cls.from_dict(json.loads(json_str)) 