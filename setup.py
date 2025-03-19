#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="callme_gate",
    version="0.1.0",
    author="Deven.Wen",
    author_email="kangqiang.w@gmail.com",
    description="一个简单的低负载联网网关，提供HTTP请求路由和处理功能",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/DevenWen/callme_gate",
    packages=find_packages(include=["callme", "callme.*"]),
    py_modules=["gate", "worker"],
    install_requires=requirements,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10"
) 