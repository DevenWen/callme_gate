import unittest
import json
import time
import threading
import uuid
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from lib.redis_client import RedisClient
from lib.router import route_registry, job_dispatcher, Node, NodeStatus
from lib.model.http_job import HttpJob, JobStatus
from lib.model.job_repository import http_job_repository

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

class TestServiceDiscovery(unittest.TestCase):
    """测试服务发现模块"""
    
    def setUp(self):
        """测试前准备"""
        self.redis = RedisClient()
        # 清理测试数据
        self.cleanup_test_data()
        
    def tearDown(self):
        """测试后清理"""
        self.cleanup_test_data()
        
    def cleanup_test_data(self):
        """清理测试数据"""
        # 清理测试路由
        test_routes = self.redis.get(ROUTES_KEY, {})
        for route_id in list(test_routes.keys()):
            if route_id.endswith('/test'):
                del test_routes[route_id]
        self.redis.set(ROUTES_KEY, test_routes)
        
        # 清理测试节点
        test_nodes = self.redis.get(NODES_KEY, {})
        for worker_id in list(test_nodes.keys()):
            if worker_id.startswith('test-worker-'):
                del test_nodes[worker_id]
        self.redis.set(NODES_KEY, test_nodes)
        
        # 清理测试路由-节点映射
        for route_id in ["GET:/api/test", "POST:/api/test"]:
            route_nodes_key = f"{ROUTE_NODES_PREFIX}:{route_id}"
            self.redis.client.delete(route_nodes_key)
            
        # 清理测试节点-路由映射
        for worker_id in ["test-worker-1", "test-worker-2"]:
            node_routes_key = f"{NODE_ROUTES_PREFIX}:{worker_id}"
            self.redis.client.delete(node_routes_key)
            
        # 清理测试队列
        for worker_id in ["test-worker-1", "test-worker-2"]:
            queue_name = f"worker_queue:{worker_id}"
            self.redis.client.delete(queue_name)
        
    def test_register_route(self):
        """测试路由注册功能"""
        # 注册测试路由
        path = "/api/test"
        method = "GET"
        worker_id = "test-worker-1"
        version = "v1"
        queue = f"worker_queue:{worker_id}"
        timeout = 10
        
        # 注册路由
        result = route_registry.register_route(path, method, worker_id, version, queue, timeout)
        self.assertTrue(result, "路由注册应该成功")
        
        # 验证路由是否注册成功
        routes = route_registry.get_all_routes()
        route_id = f"{method}:{path}"
        self.assertIn(route_id, routes, "路由应该存在于注册表中")
        
        route = routes[route_id]
        workers = route.get_workers()
        self.assertEqual(1, len(workers), "路由应该有一个工作节点")
        self.assertEqual(worker_id, workers[0]["worker_id"], "工作节点ID应该正确")
        self.assertEqual(version, workers[0]["version"], "版本应该正确")
        self.assertEqual(queue, workers[0]["queue"], "队列应该正确")
        self.assertEqual(timeout, route.timeout, "超时设置应该正确")
        
        # 验证版本集合
        versions = route.get_versions()
        self.assertIn(version, versions, "版本应该存在于版本列表中")
        
        # 验证节点信息
        node = route_registry.get_node(worker_id)
        self.assertIsNotNone(node, "节点应该存在")
        self.assertEqual(worker_id, node.worker_id, "节点ID应该正确")
        self.assertEqual(version, node.version, "节点版本应该正确")
        self.assertEqual(queue, node.queue, "节点队列应该正确")
        self.assertIn(route_id, node.routes, "节点应该关联到路由")
        
    def test_unregister_route(self):
        """测试取消注册路由功能"""
        # 先注册测试路由
        path = "/api/test"
        method = "GET"
        worker_id = "test-worker-1"
        version = "v1"
        queue = f"worker_queue:{worker_id}"
        route_registry.register_route(path, method, worker_id, version, queue)
        
        # 取消注册
        result = route_registry.unregister_route(path, method, worker_id)
        self.assertTrue(result, "取消注册应该成功")
        
        # 验证路由是否已取消注册
        route = route_registry.get_route(path, method)
        self.assertIsNone(route, "路由不应该存在") 
        
        # 验证节点-路由关系
        node = route_registry.get_node(worker_id)
        self.assertIsNotNone(node, "节点仍然应该存在")
        route_id = f"{method}:{path}"
        self.assertNotIn(route_id, node.routes, "节点不应该关联到该路由")
        
    def test_node_management(self):
        """测试节点管理功能"""
        # 注册测试节点
        worker_id = "test-worker-1"
        version = "v1"
        queue = f"worker_queue:{worker_id}"
        
        # 注册节点
        result = route_registry.register_node(worker_id, version, queue)
        self.assertTrue(result, "节点注册应该成功")
        
        # 验证节点是否注册成功
        node = route_registry.get_node(worker_id)
        self.assertIsNotNone(node, "节点应该存在")
        self.assertEqual(worker_id, node.worker_id, "节点ID应该正确")
        self.assertEqual(version, node.version, "节点版本应该正确")
        self.assertEqual(queue, node.queue, "节点队列应该正确")
        self.assertEqual(NodeStatus.ONLINE, node.status, "节点状态应该是在线")
        
        # 更新节点状态
        route_registry.update_node_status(worker_id, NodeStatus.BUSY)
        node = route_registry.get_node(worker_id)
        self.assertEqual(NodeStatus.BUSY, node.status, "节点状态应该已更新")
        
        # 测试心跳
        # 先将上次心跳时间调整为很久以前
        node.last_heartbeat = int(time.time()) - 100
        route_registry.save_node(node)
        
        # 验证节点不再存活
        node = route_registry.get_node(worker_id)
        self.assertFalse(node.is_alive(), "节点应该不存活")
        
        # 发送心跳更新
        result = route_registry.node_heartbeat(worker_id)
        self.assertTrue(result, "心跳更新应该成功")
        
        # 验证节点现在存活且状态为在线
        node = route_registry.get_node(worker_id)
        self.assertTrue(node.is_alive(), "节点应该存活")
        self.assertEqual(NodeStatus.ONLINE, node.status, "节点状态应该是在线")
        
        # 取消注册节点
        result = route_registry.unregister_node(worker_id)
        self.assertTrue(result, "取消注册节点应该成功")
        
        # 验证节点状态
        node = route_registry.get_node(worker_id)
        self.assertEqual(NodeStatus.OFFLINE, node.status, "节点状态应该是离线")
        
    def test_dispatch_job(self):
        """测试作业分发功能"""
        # 注册测试路由
        path = "/api/test"
        method = "POST"
        worker_id = "test-worker-1"
        version = "v1"
        queue = f"worker_queue:{worker_id}"
        route_registry.register_route(path, method, worker_id, version, queue)
        
        # 创建测试作业
        job = HttpJob(method=method, path=path, json_data={"test": "data"})
        http_job_repository.save(job)
        
        # 分发作业
        success, selected_worker = job_dispatcher.dispatch_job(job.request_id, path, method)
        self.assertTrue(success, "作业分发应该成功")
        self.assertEqual(worker_id, selected_worker.get("worker_id"), "应该选择正确的工作节点")
        self.assertEqual(version, selected_worker.get("version"), "应该有正确的版本")
        
        # 验证作业是否加入队列
        queue_len = self.redis.client.llen(queue)
        self.assertEqual(1, queue_len, "队列应该有一个作业")
        
        # 检查队列中的作业ID
        job_id = self.redis.client.rpop(queue)
        self.assertEqual(job.request_id, job_id, "队列中的作业ID应该正确")
        
    def test_multiple_workers(self):
        """测试多工作节点场景"""
        # 注册多个工作节点到同一路由
        path = "/api/test"
        method = "POST"
        
        # 注册第一个节点
        worker_id1 = "test-worker-1"
        version1 = "v1"
        queue1 = f"worker_queue:{worker_id1}"
        route_registry.register_route(path, method, worker_id1, version1, queue1)
        
        # 注册第二个节点
        worker_id2 = "test-worker-2"
        version2 = "v2"
        queue2 = f"worker_queue:{worker_id2}"
        route_registry.register_route(path, method, worker_id2, version2, queue2)
        
        # 验证路由有两个工作节点
        route = route_registry.get_route(path, method)
        self.assertIsNotNone(route, "路由应该存在")
        workers = route.get_workers()
        self.assertEqual(2, len(workers), "路由应该有两个工作节点")
        
        # 验证路由支持两个版本
        versions = route.get_versions()
        self.assertEqual(2, len(versions), "路由应该支持两个版本")
        self.assertIn(version1, versions, "应该包含第一个版本")
        self.assertIn(version2, versions, "应该包含第二个版本")
        
        # 测试特定版本路由
        # 设置路由策略为特定版本
        job_dispatcher.set_route_strategy(f"{method}:{path}", "specific_version", preferred_version=version1)
        
        # 创建测试作业并分发
        job = HttpJob(method=method, path=path, json_data={"test": "data"})
        http_job_repository.save(job)
        
        # 分发作业到v1版本
        success, selected_worker = job_dispatcher.dispatch_job(job.request_id, path, method)
        self.assertTrue(success, "作业分发应该成功")
        self.assertEqual(version1, selected_worker.get("version"), "应该选择v1版本节点")
        
        # 重置路由策略
        job_dispatcher.reset_route_strategy(f"{method}:{path}")
        
        # 设置新策略，使用特定版本v2
        job_dispatcher.set_route_strategy(f"{method}:{path}", "specific_version", preferred_version=version2)
        
        # 创建另一个作业并分发到v2版本
        job2 = HttpJob(method=method, path=path, json_data={"test": "data"})
        http_job_repository.save(job2)
        
        # 直接使用preferred_version而不是在请求数据中指定
        success, selected_worker = job_dispatcher.dispatch_job(job2.request_id, path, method)
        
        self.assertTrue(success, "作业分发应该成功")
        self.assertEqual(version2, selected_worker.get("version"), "应该选择v2版本节点")
        
    def test_result_synchronization(self):
        """测试结果同步功能"""
        # 创建测试作业和同步键
        request_id = str(uuid.uuid4())
        result = {"status": "success", "data": "test_result"}
        result_json = json.dumps(result)
        
        # 模拟工作线程发布结果
        def worker_thread():
            # 等待1秒后发布结果
            time.sleep(1)
            job_dispatcher.publish_result(request_id, result_json)
            
        # 启动工作线程
        thread = threading.Thread(target=worker_thread)
        thread.daemon = True
        thread.start()
        
        # 等待结果（应该在1秒后收到）
        start_time = time.time()
        received_result = job_dispatcher.wait_for_result(request_id, timeout=3)
        end_time = time.time()
        
        # 验证结果
        self.assertIsNotNone(received_result, "应该收到结果")
        self.assertEqual(result_json, received_result, "接收到的结果应该正确")
        
        # 验证等待时间（应该在1秒左右）
        wait_time = end_time - start_time
        self.assertGreaterEqual(wait_time, 0.9, "等待时间应该至少为1秒")
        self.assertLessEqual(wait_time, 1.5, "等待时间不应该超过1.5秒")
        
    def test_worker_job_processing(self):
        """测试完整的工作节点处理流程"""
        # 注册测试路由
        path = "/api/test"
        method = "POST"
        worker_id = "test-worker-1"
        version = "v1"
        queue = f"worker_queue:{worker_id}"
        
        # 确保重置所有路由策略
        route_id = f"{method.upper()}:{path}"
        job_dispatcher.reset_route_strategy(route_id)
        
        # 重新注册路由
        route_registry.register_route(path, method, worker_id, version, queue)
        
        # 创建测试作业
        job = HttpJob(method=method, path=path, json_data={"test": "data"})
        http_job_repository.save(job)
        
        # 模拟网关将作业分发到队列
        success, worker = job_dispatcher.dispatch_job(job.request_id, path, method)
        self.assertTrue(success, "作业分发应该成功")
        
        # 模拟工作节点处理作业并发布结果
        def worker_process():
            # 从队列获取作业ID
            _, job_id = self.redis.client.blpop(queue, 1)
            
            # 获取作业详情
            test_job = http_job_repository.get(job_id)
            self.assertIsNotNone(test_job, "应该能够获取到作业")
            
            # 处理作业
            test_job.set_response(
                status=200, 
                headers={"Content-Type": "application/json"},
                body={"result": "success"}
            )
            http_job_repository.save(test_job)
            
            # 发布结果
            job_dispatcher.publish_result(job_id, json.dumps(test_job.to_dict()))
            
        # 启动工作线程
        worker_thread = threading.Thread(target=worker_process)
        worker_thread.daemon = True
        worker_thread.start()
        
        # 模拟网关等待结果
        result_json = job_dispatcher.wait_for_result(job.request_id, timeout=3)
        self.assertIsNotNone(result_json, "应该收到处理结果")
        
        # 解析结果
        result_data = json.loads(result_json)
        result_job = HttpJob.from_dict(result_data)
        self.assertEqual(JobStatus.COMPLETED, result_job.status, "作业状态应该是已完成")
        self.assertEqual(200, result_job.response_status, "响应状态码应该是200")
        self.assertEqual("success", result_job.response_body["result"], "响应内容应该正确")
        
if __name__ == '__main__':
    unittest.main() 