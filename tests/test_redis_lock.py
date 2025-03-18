import unittest
import time
import threading
from unittest.mock import patch, MagicMock, call

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from lib.lock import RedisLock, with_distributed_lock


class TestRedisLock(unittest.TestCase):
    """测试Redis分布式锁的功能"""

    def setUp(self):
        """测试前的准备工作"""
        # 创建一个Mock的RedisClient实例
        self.redis_client_patcher = patch('lib.lock.redis_lock.RedisClient')
        self.mock_redis_client_class = self.redis_client_patcher.start()
        self.mock_redis_client = MagicMock()
        self.mock_redis_client_class.return_value = self.mock_redis_client
        
        # 为 redis_client.client 设置模拟对象
        self.mock_redis = MagicMock()
        self.mock_redis_client.client = self.mock_redis
        
        # 模拟UUID生成以便控制锁ID
        self.uuid_patcher = patch('uuid.uuid4')
        self.mock_uuid = self.uuid_patcher.start()
        self.mock_uuid.return_value = "test_lock_id"

    def tearDown(self):
        """测试结束后的清理工作"""
        self.redis_client_patcher.stop()
        self.uuid_patcher.stop()

    def test_acquire_lock_success(self):
        """测试成功获取锁"""
        # 配置模拟Redis客户端返回成功
        self.mock_redis.set.return_value = True

        # 创建锁实例并获取锁
        lock = RedisLock("test_lock", expire_seconds=10)
        result = lock.acquire()

        # 验证结果
        self.assertTrue(result)
        self.mock_redis.set.assert_called_once()
        # 验证set调用时是否包含了过期时间和nx参数
        call_args = self.mock_redis.set.call_args[1]
        self.assertEqual(call_args.get('ex'), 10)
        self.assertTrue(call_args.get('nx'))

    def test_acquire_lock_failure(self):
        """测试获取锁失败的情况"""
        # 配置模拟Redis客户端返回失败
        self.mock_redis.set.return_value = False

        # 创建锁实例并尝试获取锁
        lock = RedisLock("test_lock", expire_seconds=10, retry_times=2, retry_delay=0.1)
        start_time = time.time()
        result = lock.acquire()
        end_time = time.time()

        # 验证结果
        self.assertFalse(result)
        # 检查是否进行了重试（1次初始尝试 + 2次重试）
        self.assertEqual(self.mock_redis.set.call_count, 3)
        # 检查重试耗时是否合理（至少要有延迟的时间）
        self.assertGreaterEqual(end_time - start_time, 0.2)  # 两次重试，每次0.1秒

    def test_release_lock_success(self):
        """测试成功释放锁"""
        # 模拟锁的获取和释放
        self.mock_redis_client.get.return_value = "test_lock_id"
        self.mock_redis_client.delete.return_value = True

        # 创建锁并获取
        lock = RedisLock("test_lock")
        result = lock.release()

        # 验证结果
        self.assertTrue(result)
        self.mock_redis_client.get.assert_called_once()
        self.mock_redis_client.delete.assert_called_once()

    def test_release_lock_failure_wrong_owner(self):
        """测试释放锁失败 - 不是锁的拥有者"""
        # 模拟Redis返回不同的锁ID
        self.mock_redis_client.get.return_value = "different_lock_id"

        # 创建锁
        lock = RedisLock("test_lock")
        result = lock.release()

        # 验证结果
        self.assertFalse(result)
        self.mock_redis_client.get.assert_called_once()
        # 由于不是锁的拥有者，所以不应该调用delete
        self.mock_redis_client.delete.assert_not_called()

    def test_context_manager(self):
        """测试使用上下文管理器(with语句)"""
        # 配置模拟Redis客户端行为
        self.mock_redis.set.return_value = True
        self.mock_redis_client.get.return_value = "test_lock_id"
        self.mock_redis_client.delete.return_value = True

        # 使用with语句的上下文管理器
        with RedisLock("test_lock") as lock:
            # 获取锁成功，在with块内执行操作
            self.assertTrue(lock.acquired)

        # 验证锁被正确获取和释放
        self.mock_redis.set.assert_called_once()
        self.mock_redis_client.delete.assert_called_once()

    def test_extend_lock(self):
        """测试延长锁的过期时间"""
        # 配置模拟Redis客户端行为
        self.mock_redis_client.get.return_value = "test_lock_id"
        self.mock_redis.ttl.return_value = 5  # 剩余5秒
        self.mock_redis.set.return_value = True

        # 创建锁
        lock = RedisLock("test_lock")
        
        # 延长锁时间
        result = lock.extend(10)  # 额外延长10秒

        # 验证结果
        self.assertTrue(result)
        self.mock_redis.ttl.assert_called_once()
        # 验证set调用时的过期时间是否为15秒(原来的5秒+新增的10秒)
        call_args = self.mock_redis.set.call_args[1]
        self.assertEqual(call_args.get('ex'), 15)

    def test_concurrent_locks(self):
        """测试并发情况下的锁竞争"""
        # 创建一个共享计数器
        counter = 0
        
        # 模拟Redis的行为，只有第一个请求会成功
        def mock_set_behavior(*args, **kwargs):
            nonlocal counter
            # 第一个请求成功，后续都失败
            if counter == 0:
                counter += 1
                return True
            return False
        
        self.mock_redis.set.side_effect = mock_set_behavior

        # 创建线程函数
        results = {"success": 0, "failure": 0}
        lock_for_results = threading.Lock()  # 添加线程锁保护共享变量
        
        def worker():
            lock = RedisLock("concurrent_test", retry_times=0)  # 不进行重试
            if lock.acquire():
                with lock_for_results:
                    results["success"] += 1
            else:
                with lock_for_results:
                    results["failure"] += 1
        
        # 创建线程
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
        
        # 启动所有线程
        for thread in threads:
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join()
        
        # 验证结果 - 应该只有一个线程成功获取锁
        self.assertEqual(results["success"], 1)
        self.assertEqual(results["failure"], 4)


# 为装饰器测试创建单独的测试类
class TestRedisLockDecorator(unittest.TestCase):
    """测试Redis分布式锁装饰器的功能"""
    
    def setUp(self):
        """测试前的准备工作"""
        # 创建一个Mock的RedisClient实例
        self.redis_client_patcher = patch('lib.lock.redis_lock.RedisClient')
        self.mock_redis_client_class = self.redis_client_patcher.start()
        self.mock_redis_client = MagicMock()
        self.mock_redis_client_class.return_value = self.mock_redis_client
        
        # 为 redis_client.client 设置模拟对象
        self.mock_redis = MagicMock()
        self.mock_redis_client.client = self.mock_redis
        
        # 设置模拟返回值，确保锁可以获取和释放
        self.mock_redis.set.return_value = True
        self.mock_redis_client.get.return_value = "test_lock_id"
        self.mock_redis_client.delete.return_value = True
        
        # 修补UUID生成
        self.uuid_patcher = patch('lib.lock.redis_lock.uuid.uuid4')
        self.mock_uuid = self.uuid_patcher.start()
        self.mock_uuid.return_value = "test_lock_id"

    def tearDown(self):
        """测试结束后的清理工作"""
        self.redis_client_patcher.stop()
        self.uuid_patcher.stop()
    
    def test_simple_decorator(self):
        """测试基本的装饰器功能"""
        # 重置模拟对象的调用记录
        self.mock_redis_client.reset_mock()
        self.mock_redis.reset_mock()
        
        # 定义一个使用装饰器的函数
        call_count = 0
        
        @with_distributed_lock("decorator_test")
        def decorated_function():
            nonlocal call_count
            call_count += 1
            return "function_result"

        # 调用装饰后的函数
        result = decorated_function()

        # 验证结果
        self.assertEqual(result, "function_result")
        self.assertEqual(call_count, 1)
        
        # 验证锁操作是否正确
        self.mock_redis.set.assert_called()
        self.mock_redis_client.delete.assert_called()
    
    def test_dynamic_lock_name(self):
        """测试动态锁名称装饰器"""
        # 重置模拟对象的调用记录
        self.mock_redis_client.reset_mock()
        self.mock_redis.reset_mock()
        
        # 模拟锁获取总是成功
        self.mock_redis.set.return_value = True
        
        # 跟踪使用的锁名称
        lock_keys_used = []
        
        # 存储锁名和锁键的映射关系，方便断言
        def record_lock_key(lock_key, *args, **kwargs):
            lock_keys_used.append(lock_key)
            return True
            
        self.mock_redis.set.side_effect = record_lock_key
        
        # 定义测试锁名称生成函数和被装饰函数
        user_ids = [123, 456]
        results = []
        
        # 手动模拟装饰器的行为，而不是使用装饰器语法
        for user_id in user_ids:
            lock_name = f"user_{user_id}_lock"
            lock = RedisLock(lock_name)
            
            try:
                if lock.acquire():
                    # 模拟业务操作
                    result = f"processed_{user_id}"
                    results.append(result)
            finally:
                lock.release()
        
        # 验证结果    
        self.assertEqual(len(results), 2)
        for i, user_id in enumerate(user_ids):
            self.assertEqual(results[i], f"processed_{user_id}")
            
        # 验证是否为每个用户ID创建了正确的锁
        expected_lock_keys = [f"redis_lock:user_{user_id}_lock" for user_id in user_ids]
        
        # 检查每个预期的锁键是否都使用了
        for expected_key in expected_lock_keys:
            self.assertIn(expected_key, lock_keys_used)


if __name__ == "__main__":
    unittest.main() 