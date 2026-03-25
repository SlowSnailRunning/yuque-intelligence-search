# 使用 yuque-dl 下载语雀知识库到本地
YUQUE_DATASET_DOWNLOAD_CMD="""yuque-dl "https://zhyk.yuque.com/gwfyn2/se52ky" -d "/Users/mac/download" -i true -t "kC4Wtyjde9lU30Bjjd_G1e5XxgDxFpMjWSszfEoWTsw545_xOvqwPh4kSD9BdPgCevqh74dfSfvPauRw6KYdCA==" """

# 语雀知识库下载目录
YUQUE_DATASET_PATH=	"/Users/mac/download/交易台账组"
# 扫描多久有更新的文档，这些文档名称不在知识库时，将上传文件；否则丢弃
FILTER_YUQUE_MD_MAX_UPDATE_DAYS=10
# 最近 N 天更新的文档，直接更新到知识库，不关心是否发生了文件变动
UPDATE_DATASET_FILE_MAX_DAYS=2



# Dify API 配置
DIFY_BASE_URL = "http://dify.shebao.net/v1"
DIFY_DATASET_ID = "7415abce-25ba-47d0-8013-ed9f7344b9b3"
DIFY_DATASET_API_KEY = "dataset-yOVQ0jOZSWoA4ORKdrB8sn5o"

# Dify Embedding 配置
EMBEDDING_MODEL = "text-embedding-v3"
EMBEDDING_DIMENSION = 1024
