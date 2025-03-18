import unittest
import json
import os
import sys

# 添加项目根目录到系统路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gate import app
from lib.model.http_job import HttpJob
from lib.model.job_repository import http_job_repository
from lib.redis_client import RedisClient

class TestHttpJob(unittest.TestCase):
    """测试HTTP作业模块"""
    
    def setUp(self):
        """测试前准备"""
        self.app = app.test_client()
        self.app_context = app.app_context()
        self.app_context.push()
        
        # 确保Redis可用
        self.redis = RedisClient()
        try:
            self.redis.client.ping()
        except Exception as e:
            self.skipTest(f"Redis不可用: {e}")
    
    def tearDown(self):
        """测试后清理"""
        self.app_context.pop()
    
    def test_create_http_job(self):
        """测试创建HTTP作业"""
        job = HttpJob(
            method="GET",
            path="/test",
            headers={"User-Agent": "Test"},
            query_params={"q": "test"}
        )
        
        self.assertEqual(job.method, "GET")
        self.assertEqual(job.path, "/test")
        self.assertEqual(job.headers.get("User-Agent"), "Test")
        self.assertEqual(job.query_params.get("q"), "test")
    
    def test_http_job_serialization(self):
        """测试HTTP作业序列化和反序列化"""
        job = HttpJob(
            method="POST",
            path="/api/data",
            headers={"Content-Type": "application/json"},
            json_data={"name": "test"}
        )
        
        # 测试序列化
        job_dict = job.to_dict()
        self.assertEqual(job_dict["method"], "POST")
        self.assertEqual(job_dict["path"], "/api/data")
        self.assertEqual(job_dict["json"]["name"], "test")
        
        # 测试反序列化
        job2 = HttpJob.from_dict(job_dict)
        self.assertEqual(job2.method, "POST")
        self.assertEqual(job2.path, "/api/data")
        self.assertEqual(job2.json_data["name"], "test")

if __name__ == '__main__':
    unittest.main() 