# 
rm -rf tabulate
rm -rf tabulate-0.9.0.dist-info

pip install -t . tabulate

# 获取当前时间戳
timestamp=$(date +%Y%m%d%H%M%S)
# 获取git最近一次提交的前7位字符
commit_hash=$(git rev-parse --short HEAD)

zip_filename="build/code-${timestamp}-${commit_hash}.zip"
zip $zip_filename -r ./*

# 清理文件
rm -rf tabulate
rm -rf tabulate-0.9.0.dist-info

