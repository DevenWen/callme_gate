import unittest
import json
import os
import sys
import time
import threading
import requests
from unittest.mock import MagicMock, patch

# 添加项目根目录到系统路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from callme.redis_client import RedisClient
from callme.model.job_repository import http_job_repository
from callme.app_worker import worker, start_worker, stop_worker, register_handler, AppWorker
from callme.model.http_job import HttpJob, JobStatus
from examples.counter import counter

# 创建 Redis 客户端的模拟
mock_redis = MagicMock()
mock_redis.ping.return_value = True
mock_redis.blpop.return_value = None
mock_redis.rpush.return_value = True
mock_redis.client = mock_redis  # 为了兼容一些调用方式

# 测试处理器函数
def test_echo(job: HttpJob):
    """测试回显处理器"""
    return job.json_data or {"message": "No data"}

def increment_counter_handler(job: HttpJob):
    """测试计数器增加处理器"""
    data = job.json_data or {}
    counter_name = data.get("name", "default")
    amount = int(data.get("amount", 1))
    new_value = counter.increment(counter_name, amount)
    return {
        "counter_name": counter_name,
        "value": new_value,
        "operation": "increment",
        "amount": amount
    }

def decrement_counter_handler(job: HttpJob):
    """测试计数器减少处理器"""
    data = job.json_data or {}
    counter_name = data.get("name", "default")
    amount = int(data.get("amount", 1))
    new_value = counter.decrement(counter_name, amount)
    return {
        "counter_name": counter_name,
        "value": new_value,
        "operation": "decrement",
        "amount": amount
    }

def reset_counter_handler(job: HttpJob):
    """测试计数器重置处理器"""
    data = job.json_data or {}
    counter_name = data.get("name", "default")
    success = counter.reset(counter_name)
    return {
        "counter_name": counter_name,
        "value": 0,
        "operation": "reset",
        "success": success
    }

def get_counter_handler(job: HttpJob):
    """测试计数器获取处理器"""
    query_params = job.query_params or {}
    counter_name = query_params.get("name", ["default"])[0]
    value = counter.get(counter_name)
    return {
        "counter_name": counter_name,
        "value": value
    }

class TestGatewayWorker(unittest.TestCase):
    """测试网关-工作节点架构"""
    
    @classmethod
    @patch('lib.redis_client.redis.Redis', return_value=mock_redis)
    @patch('lib.redis_client.RedisClient', return_value=mock_redis)
    def setUpClass(cls, mock_redis_client, mock_redis_lib):
        """测试前准备，创建自己的工作节点而不使用全局工作节点"""
        # 确保没有全局工作节点运行
        stop_worker()
        
        # 创建测试专用工作节点
        cls.test_worker = AppWorker(worker_version="test_worker")
        
        # 注册处理器
        cls.test_worker.register_handler("/api/test/echo", "POST", test_echo)
        cls.test_worker.register_handler("/api/counter/increment", "POST", increment_counter_handler)
        cls.test_worker.register_handler("/api/counter/decrement", "POST", decrement_counter_handler)
        cls.test_worker.register_handler("/api/counter/reset", "POST", reset_counter_handler)
        cls.test_worker.register_handler("/api/counter/get", "GET", get_counter_handler)
        
        # 设置全局模拟
        global mock_redis
        
        # 配置 http_job_repository 使用模拟的 Redis
        http_job_repository.redis = mock_redis
        
        # 启动工作节点
        cls.test_worker.start()
        
        # 等待工作节点启动
        time.sleep(0.2)
        
        # 为测试准备模拟数据
        cls.test_job_data = {
            "status": JobStatus.COMPLETED,
            "response_status": 200,
            "response_headers": {"Content-Type": "application/json"},
            "response_body": {"message": "Hello, Worker!"}
        }
    
    @classmethod
    def tearDownClass(cls):
        """测试后清理，停止工作节点"""
        if hasattr(cls, 'test_worker') and cls.test_worker:
            cls.test_worker.stop()
    
    def setUp(self):
        """每个测试前清理相关数据"""
        # 清理测试计数器
        counter.delete("test_counter")
        # 重置模拟对象
        global mock_redis
        mock_redis.reset_mock()
    
    @patch('callme.model.job_repository.http_job_repository.get')
    def test_direct_worker_processing(self, mock_get):
        """测试工作节点直接处理作业"""
        # 模拟作业处理完成
        test_job = HttpJob(
            method="POST",
            path="/api/test/echo",
            json_data={"message": "Hello, Worker!"}
        )
        test_job.update_status(JobStatus.COMPLETED)
        test_job.set_response(
            status=200,
            headers={"Content-Type": "application/json"},
            body={"message": "Hello, Worker!"}
        )
        mock_get.return_value = test_job
        
        # 设置 blpop 返回模拟的请求 ID
        global mock_redis
        mock_redis.blpop.return_value = (None, test_job.request_id)
        
        # 创建测试作业
        job = HttpJob(
            method="POST",
            path="/api/test/echo",
            json_data={"message": "Hello, Worker!"}
        )
        
        # 将作业添加到队列
        queue_name = self.__class__.test_worker.get_queue_name()
        mock_redis.rpush(queue_name, job.request_id)
        
        # 等待短暂时间，让工作节点处理队列
        time.sleep(0.2)
        
        # 断言 Redis 操作被调用
        mock_redis.rpush.assert_called()
        
        # 获取更新后的作业
        updated_job = http_job_repository.get(job.request_id)
        
        # 验证作业已处理
        self.assertIsNotNone(updated_job, "作业未找到")
        self.assertEqual(updated_job.status, JobStatus.COMPLETED)
        self.assertEqual(updated_job.response_body["message"], "Hello, Worker!")
    
    def test_counter_increment(self):
        """测试计数器增加功能"""
        # 初始值
        self.assertEqual(counter.get("test_counter"), 0)
        
        # 直接调用处理函数
        job = HttpJob(
            method="POST",
            path="/api/counter/increment",
            json_data={"name": "test_counter", "amount": 5}
        )
        
        # 调用处理函数
        result = increment_counter_handler(job)
        
        # 验证结果
        self.assertEqual(result["counter_name"], "test_counter")
        self.assertEqual(result["value"], 5)
        
        # 验证计数器已增加
        self.assertEqual(counter.get("test_counter"), 5)
        
        # 清理
        counter.delete("test_counter")

# 如果直接运行脚本，执行测试
if __name__ == '__main__':
    unittest.main() 