#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量上传 Markdown 文档到 Dify 知识库
功能：
1. 从指定目录筛选符合条件的 Markdown 文件
2. 解析文件末尾的时间戳，筛选最近N天内更新的文档
3. 通过API获取知识库现有文档列表，进行状态比对
4. 自动创建新文档或更新已有文档
"""

import os
import re
import json
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 导入常量
from constants import *



class MarkdownFilter:
    """Markdown 文件筛选器"""
    
    def __init__(self, source_path: str):
        self.source_path = Path(source_path)
        # 时间戳正则表达式：匹配 "更新: YYYY-MM-DD HH:MM:SS" 格式
        self.timestamp_pattern = re.compile(
            r'更新[:：]\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',
            re.MULTILINE
        )
        # 最近 N 天的时间阈值
        self.cutoff_date = datetime.now() - timedelta(days=FILTER_YUQUE_MD_MAX_UPDATE_DAYS)
    
    def is_valid_markdown(self, file_path: Path) -> Tuple[bool, Optional[str]]:
        """
        检查文件是否为有效的 Markdown 文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            (是否有效, 错误信息)
        """
        if not file_path.suffix.lower() in ['.md', '.markdown']:
            return False, f"不是 Markdown 文件: {file_path.suffix}"
        return True, None
    
    def should_filter_by_name(self, file_path: Path) -> Tuple[bool, Optional[str]]:
        """
        根据文件名过滤
        
        Args:
            file_path: 文件路径
            
        Returns:
            (是否过滤, 原因)
        """
        # 过滤 index.md
        if file_path.name.lower() == 'index.md':
            return True, "文件名是 index.md"
        return False, None
    
    def should_filter_by_path(self, file_path: Path) -> Tuple[bool, Optional[str]]:
        """
        根据文件路径过滤
        
        Args:
            file_path: 文件路径
            
        Returns:
            (是否过滤, 原因)
        """
        # 过滤路径中包含"周报"的文件
        if '周报' in str(file_path):
            return True, "路径包含'周报'"
        return False, None
    
    def should_filter_by_content_length(self, content: str) -> Tuple[bool, Optional[str]]:
        """
        根据内容长度过滤
        
        Args:
            content: 文件内容
            
        Returns:
            (是否过滤, 原因)
        """
        if len(content) < 1000:
            return True, f"内容长度 {len(content)} 小于 1000 字符"
        return False, None
    
    def extract_timestamp(self, content: str) -> Tuple[Optional[datetime], Optional[str]]:
        """
        从文件内容中提取时间戳
        
        Args:
            content: 文件内容
            
        Returns:
            (时间戳, 错误信息)
        """
        # 在文件末尾查找时间戳（最后500个字符内）
        search_content = content[-500:] if len(content) > 500 else content
        
        matches = self.timestamp_pattern.findall(search_content)
        if not matches:
            return None, "未找到时间戳格式 '更新: YYYY-MM-DD HH:MM:SS'"
        
        # 使用最后一个匹配的时间戳
        timestamp_str = matches[-1]
        try:
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
            return timestamp, None
        except ValueError as e:
            return None, f"时间戳解析失败: {e}"
    
    def should_filter_by_timestamp(self, timestamp: datetime) -> Tuple[bool, Optional[str]]:
        """
        根据时间戳过滤（只保留最近5天内的）
        
        Args:
            timestamp: 文件时间戳
            
        Returns:
            (是否过滤, 原因)
        """
        if timestamp < self.cutoff_date:
            days_ago = (datetime.now() - timestamp).days
            return True, f"文件更新于 {days_ago} 天前，超过限制"
        return False, None
    
    def process_file(self, file_path: Path) -> Tuple[Optional[Dict], Optional[str]]:
        """
        处理单个 Markdown 文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            (文件信息字典, 错误信息)
        """
        # 检查是否为有效的 Markdown 文件
        is_valid, error = self.is_valid_markdown(file_path)
        if not is_valid:
            return None, error
        
        # 按文件名过滤
        should_filter, reason = self.should_filter_by_name(file_path)
        if should_filter:
            return None, f"被文件名过滤: {reason}"
        
        # 按路径过滤
        should_filter, reason = self.should_filter_by_path(file_path)
        if should_filter:
            return None, f"被路径过滤: {reason}"
        
        # 读取文件内容
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='gbk') as f:
                    content = f.read()
            except Exception as e:
                return None, f"文件编码错误: {e}"
        except Exception as e:
            return None, f"读取文件失败: {e}"
        
        # 按内容长度过滤
        should_filter, reason = self.should_filter_by_content_length(content)
        if should_filter:
            return None, f"被内容长度过滤: {reason}"
        
        # 提取时间戳
        timestamp, error = self.extract_timestamp(content)
        if timestamp is None:
            return None, f"时间戳提取失败: {error}"
        
        # 按时间戳过滤
        should_filter, reason = self.should_filter_by_timestamp(timestamp)
        if should_filter:
            return None, f"被时间戳过滤: {reason}"
        
        # 构建文件信息字典
        file_info = {
            'file_path': str(file_path),
            'file_name': file_path.name,
            'relative_path': str(file_path.relative_to(self.source_path)),
            'content': content,
            'content_length': len(content),
            'update_timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'update_timestamp_obj': timestamp
        }
        
        return file_info, None
    
    def scan_directory(self) -> Dict[str, Dict]:
        """
        扫描目录，筛选符合条件的 Markdown 文件
        
        Returns:
            包含所有通过筛选的文件信息的字典
        """
        result = {
            'source_path': str(self.source_path),
            'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_files': 0,
            'passed_files': 0,
            'filtered_files': 0,
            'files': {},
            'errors': []
        }
        
        if not self.source_path.exists():
            result['errors'].append(f"源路径不存在: {self.source_path}")
            return result
        
        if not self.source_path.is_dir():
            result['errors'].append(f"源路径不是目录: {self.source_path}")
            return result
        
        # 遍历目录中的所有 Markdown 文件
        markdown_files = list(self.source_path.rglob('*.md')) + list(self.source_path.rglob('*.markdown'))
        
        logger.info(f"开始扫描目录: {self.source_path}")
        logger.info(f"找到 {len(markdown_files)} 个 Markdown 文件")
        
        for file_path in markdown_files:
            result['total_files'] += 1
            
            file_info, error = self.process_file(file_path)
            
            if file_info:
                # 使用相对路径作为键
                key = file_info['relative_path']
                result['files'][key] = file_info
                result['passed_files'] += 1
                logger.info(f"✓ 通过筛选: {key} (更新于: {file_info['update_timestamp']})")
            else:
                result['filtered_files'] += 1
                filter_info = {
                    'file_path': str(file_path),
                    'reason': error
                }
                result['errors'].append(filter_info)
                logger.debug(f"✗ 过滤文件: {file_path.name} - {error}")
        
        logger.info(f"扫描完成: 总计 {result['total_files']} 个文件, "
                   f"通过 {result['passed_files']} 个, 过滤 {result['filtered_files']} 个")
        
        return result


class DifyDocumentManager:
    """Dify 知识库文档管理器 - 处理API交互"""
    
    def __init__(self, api_key: str = DIFY_DATASET_API_KEY, base_url: str = DIFY_BASE_URL, dataset_id: str = DIFY_DATASET_ID):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.dataset_id = dataset_id
        self.headers = {
            "Authorization": f"Bearer {api_key}"
        }
    
    def get_existing_documents(self, page: int = 1, limit: int = 100) -> Dict[str, str]:
        """
        获取知识库中现有的文档列表
        
        Returns:
            字典: {文件名: 文档ID}
        """
        documents = {}
        current_page = page
        
        while True:
            url = f"{self.base_url}/datasets/{self.dataset_id}/documents?page={current_page}&limit={limit}"
            
            try:
                logger.info(f"正在获取知识库文档列表，第 {current_page} 页...")
                response = requests.get(url, headers=self.headers, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                docs_data = data.get('data', [])
                
                if not docs_data:
                    break
                
                for doc in docs_data:
                    doc_name = doc.get('name', '')
                    doc_id = doc.get('id', '')
                    if doc_name and doc_id:
                        documents[doc_name] = doc_id
                
                # 检查是否还有更多页
                has_more = data.get('has_more', False)
                if not has_more:
                    break
                
                current_page += 1
                time.sleep(0.5)  # 避免请求过快
                
            except requests.exceptions.RequestException as e:
                logger.error(f"获取文档列表失败: {e}")
                break
            except json.JSONDecodeError as e:
                logger.error(f"解析响应JSON失败: {e}")
                break
        
        logger.info(f"知识库中共有 {len(documents)} 个文档")
        return documents
    
    def _build_upload_data(self, file_id: Optional[str] = None) -> str:
        """
        构建上传数据的JSON字符串（与Dify后台API要求完全一致）
        
        Args:
            file_id: 文件ID（更新文档时使用）
            
        Returns:
            JSON字符串
        """
        # 构建 data_source 部分
        if file_id:
            # 更新文档时使用 file_id
            data_source = {
                "type": "upload_file",
                "info_list": {
                    "data_source_type": "upload_file",
                    "file_info_list": {
                        "file_ids": [file_id]
                    }
                }
            }
        else:
            # 创建文档时不需要 data_source（通过file字段上传）
            data_source = None
        
        data = {
            "indexing_technique": "high_quality",
            "process_rule": {
                "mode": "custom",
                "rules": {
                    "pre_processing_rules": [
                        {"id": "remove_extra_spaces", "enabled": True},
                        {"id": "remove_urls_emails", "enabled": False}
                    ],
                    "segmentation": {
                        "separator": "\n\n",
                        "max_tokens": 1024,
                        "chunk_overlap": 50
                    }
                }
            },
            "doc_form": "text_model",
            "doc_language": "Chinese Simplified",
            "retrieval_model": {
                "search_method": "hybrid_search",
                "reranking_enable": True,
                "reranking_mode": "weighted_score",
                "reranking_model": {
                    "reranking_provider_name": "langgenius/tongyi/tongyi",
                    "reranking_model_name": "gte-rerank"
                },
                "weights": {
                    "weight_type": "customized",
                    "vector_setting": {
                        "vector_weight": 0.7,
                        "embedding_provider_name": "",
                        "embedding_model_name": ""
                    },
                    "keyword_setting": {
                        "keyword_weight": 0.3
                    }
                },
                "top_k": 2,
                "score_threshold_enabled": False,
                "score_threshold": 0
            },
            "embedding_model": EMBEDDING_MODEL,
            "embedding_model_provider": "langgenius/tongyi/tongyi"
        }
        
        # 只有在更新文档时才添加 data_source
        if data_source:
            data["data_source"] = data_source
        
        return json.dumps(data, ensure_ascii=False)
    
    def create_document(self, file_info: Dict) -> Tuple[bool, Optional[str]]:
        """
        创建新文档
        
        Args:
            file_info: 文件信息字典
            
        Returns:
            (是否成功, 文档ID或错误信息)
        """
        url = f"{self.base_url}/datasets/{self.dataset_id}/document/create-by-file"
        
        try:
            # 将内容写入临时文件
            file_path = file_info['file_path']
            file_name = file_info['file_name']
            
            with open(file_path, 'rb') as f:
                files = {
                    'file': (file_name, f, 'text/markdown')
                }
                data = {
                    'data': (None, self._build_upload_data(), 'text/plain')
                }
                
                logger.info(f"正在创建文档: {file_name}")
                response = requests.post(url, headers=self.headers, files=files, data=data, timeout=60)
                response.raise_for_status()
                
                result = response.json()
                document_id = result.get('document', {}).get('id')
                
                if document_id:
                    logger.info(f"✓ 文档创建成功: {file_name} (ID: {document_id})")
                    return True, document_id
                else:
                    logger.error(f"✗ 文档创建失败: {file_name} - 响应中无文档ID")
                    return False, "响应中无文档ID"
                    
        except requests.exceptions.RequestException as e:
            error_msg = f"创建文档请求失败: {e}"
            logger.error(f"✗ {file_name} - {error_msg}")
            return False, error_msg
        except Exception as e:
            error_msg = f"创建文档异常: {e}"
            logger.error(f"✗ {file_name} - {error_msg}")
            return False, error_msg
    
    def update_document(self, file_info: Dict, document_id: str) -> Tuple[bool, Optional[str]]:
        """
        更新已有文档
        
        参考cmd.shell示例，使用multipart/form-data格式直接上传文件
        
        Args:
            file_info: 文件信息字典
            document_id: 文档ID
            
        Returns:
            (是否成功, 错误信息)
        """
        url = f"{self.base_url}/datasets/{self.dataset_id}/documents/{document_id}/update-by-file"

        try:
            file_path = file_info['file_path']
            file_name = file_info['file_name']

            with open(file_path, 'rb') as f:
                # multipart/form-data 格式，与create_document保持一致
                files = {
                    'file': (file_name, f, 'text/markdown')
                }
                # data字段包含name和process_rule等配置
                data = {
                    'data': (None, self._build_update_data(file_name), 'text/plain')
                }

                logger.info(f"正在更新文档: {file_name} (文档ID: {document_id})")
                response = requests.post(
                    url,
                    headers=self.headers,
                    files=files,
                    data=data,
                    timeout=60
                )
                response.raise_for_status()

                result = response.json()
                updated_id = result.get('document', {}).get('id')

                if updated_id:
                    logger.info(f"✓ 文档更新成功: {file_name} (ID: {updated_id})")
                    return True, None
                else:
                    logger.error(f"✗ 文档更新失败: {file_name} - 响应异常")
                    return False, "响应异常"

        except requests.exceptions.RequestException as e:
            error_msg = f"更新文档请求失败: {e}"
            logger.error(f"✗ {file_name} - {error_msg}")
            return False, error_msg
        except Exception as e:
            error_msg = f"更新文档异常: {e}"
            logger.error(f"✗ {file_name} - {error_msg}")
            return False, error_msg

    def _build_update_data(self, file_name: str) -> str:
        """
        构建更新文档的data参数（与create_document类似，但包含name字段）
        
        Args:
            file_name: 文件名
            
        Returns:
            JSON字符串
        """
        data = {
            "name": file_name,
            "indexing_technique": "high_quality",
            "process_rule": {
                "mode": "custom",
                "rules": {
                    "pre_processing_rules": [
                        {"id": "remove_extra_spaces", "enabled": True},
                        {"id": "remove_urls_emails", "enabled": False}
                    ],
                    "segmentation": {
                        "separator": "\n\n",
                        "max_tokens": 1024,
                        "chunk_overlap": 50
                    }
                }
            },
            "doc_form": "text_model",
            "doc_language": "Chinese Simplified",
            "retrieval_model": {
                "search_method": "hybrid_search",
                "reranking_enable": True,
                "reranking_mode": "weighted_score",
                "reranking_model": {
                    "reranking_provider_name": "langgenius/tongyi/tongyi",
                    "reranking_model_name": "gte-rerank"
                },
                "weights": {
                    "weight_type": "customized",
                    "vector_setting": {
                        "vector_weight": 0.7,
                        "embedding_provider_name": "",
                        "embedding_model_name": ""
                    },
                    "keyword_setting": {
                        "keyword_weight": 0.3
                    }
                },
                "top_k": 2,
                "score_threshold_enabled": False,
                "score_threshold": 0
            },
            "embedding_model": EMBEDDING_MODEL,
            "embedding_model_provider": "langgenius/tongyi/tongyi"
        }
        return json.dumps(data, ensure_ascii=False)


class DocumentSyncManager:
    """文档同步管理器 - 协调本地文件与知识库状态"""
    
    def __init__(self, dify_manager: DifyDocumentManager, cutoff_days: int = 3):
        self.dify_manager = dify_manager
        self.cutoff_date = datetime.now() - timedelta(days=cutoff_days)
    
    def sync_documents(self, local_files: Dict[str, Dict]) -> Dict:
        """
        同步本地文档到知识库
        
        Args:
            local_files: 本地文件字典 {相对路径: 文件信息}
            
        Returns:
            同步结果统计
        """
        result = {
            'total': len(local_files),
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'failed': 0,
            'details': []
        }
        
        # 获取知识库现有文档
        existing_docs = self.dify_manager.get_existing_documents()
        
        logger.info(f"\n{'='*60}")
        logger.info("开始文档同步")
        logger.info(f"{'='*60}")
        logger.info(f"本地待处理文件: {len(local_files)} 个")
        logger.info(f"知识库现有文档: {len(existing_docs)} 个")
        
        for relative_path, file_info in local_files.items():
            file_name = file_info['file_name']
            update_time = datetime.strptime(file_info['update_timestamp'], '%Y-%m-%d %H:%M:%S')
            
            sync_detail = {
                'file_name': file_name,
                'relative_path': relative_path,
                'action': '',
                'success': False,
                'message': ''
            }
            
            # 检查文件是否已存在于知识库
            if file_name in existing_docs:
                document_id = existing_docs[file_name]
                
                # 检查是否在3天内更新
                if update_time >= self.cutoff_date:
                    # 更新文档
                    success, error = self.dify_manager.update_document(file_info, document_id)
                    if success:
                        result['updated'] += 1
                        sync_detail['action'] = 'UPDATE'
                        sync_detail['success'] = True
                        sync_detail['message'] = f"文档已更新 (ID: {document_id})"
                    else:
                        result['failed'] += 1
                        sync_detail['action'] = 'UPDATE_FAILED'
                        sync_detail['message'] = error
                else:
                    # 跳过（超过3天）
                    result['skipped'] += 1
                    sync_detail['action'] = 'SKIP'
                    sync_detail['success'] = True
                    sync_detail['message'] = f"文档已存在且超过3天未更新 (ID: {document_id})"
                    logger.info(f"⊘ 跳过文档: {file_name} (超过3天未更新)")
            else:
                # 创建新文档
                success, doc_id_or_error = self.dify_manager.create_document(file_info)
                if success:
                    result['created'] += 1
                    sync_detail['action'] = 'CREATE'
                    sync_detail['success'] = True
                    sync_detail['message'] = f"文档已创建 (ID: {doc_id_or_error})"
                else:
                    result['failed'] += 1
                    sync_detail['action'] = 'CREATE_FAILED'
                    sync_detail['message'] = doc_id_or_error
            
            result['details'].append(sync_detail)
            time.sleep(0.5)  # 避免请求过快
        
        return result


def query_need_process_files():
    """查询需要处理的文件列表"""
    # 创建文件筛选器
    filter_processor = MarkdownFilter(YUQUE_DATASET_PATH)
    
    # 扫描目录并筛选文件
    scan_result = filter_processor.scan_directory()
    
    # 打印结果摘要
    print("\n" + "="*60)
    print("扫描结果摘要")
    print("="*60)
    print(f"源目录: {scan_result['source_path']}")
    print(f"扫描时间: {scan_result['scan_time']}")
    print(f"总文件数: {scan_result['total_files']}")
    print(f"通过筛选: {scan_result['passed_files']}")
    print(f"被过滤: {scan_result['filtered_files']}")
    
    # 显示部分过滤原因（最多显示10条）
    filter_reasons = [e for e in scan_result['errors'] if isinstance(e, dict)]
    if filter_reasons:
        print("\n部分被过滤的文件原因 (显示前10条):")
        print("-"*60)
        for item in filter_reasons[:10]:
            print(f"• {Path(item['file_path']).name}: {item['reason']}")
        if len(filter_reasons) > 10:
            print(f"... 还有 {len(filter_reasons) - 10} 条过滤记录")
    
    return scan_result


def sync_to_dify(scan_result: Dict):
    """
    将扫描结果同步到 Dify 知识库
    
    Args:
        scan_result: 扫描结果字典
    """
    if not scan_result.get('files'):
        logger.info("没有需要同步的文件")
        return
    
    # 创建 Dify 文档管理器
    dify_manager = DifyDocumentManager()
    
    # 创建同步管理器（3天内更新的文件才更新，其他的跳过）
    sync_manager = DocumentSyncManager(dify_manager, cutoff_days=UPDATE_DATASET_FILE_MAX_DAYS)
    
    # 执行同步
    sync_result = sync_manager.sync_documents(scan_result['files'])
    
    # 打印同步结果
    print("\n" + "="*60)
    print("文档同步结果")
    print("="*60)
    print(f"总计: {sync_result['total']} 个文件")
    print(f"新建: {sync_result['created']} 个")
    print(f"更新: {sync_result['updated']} 个")
    print(f"跳过: {sync_result['skipped']} 个")
    print(f"失败: {sync_result['failed']} 个")
    
    # 显示详细信息
    if sync_result['details']:
        print("\n详细同步记录:")
        print("-"*60)
        for detail in sync_result['details']:
            status_icon = "✓" if detail['success'] else "✗"
            action_desc = {
                'CREATE': '新建',
                'UPDATE': '更新',
                'SKIP': '跳过',
                'CREATE_FAILED': '创建失败',
                'UPDATE_FAILED': '更新失败'
            }.get(detail['action'], detail['action'])
            
            print(f"{status_icon} [{action_desc}] {detail['file_name']}")
            if detail['message']:
                print(f"   └─ {detail['message']}")


def main():
    """主函数"""
    # 第一步：扫描并筛选文件
    scan_result = query_need_process_files()
    
    # 第二步：同步到 Dify
    if scan_result.get('files'):
        sync_to_dify(scan_result)
    else:
        logger.info("没有符合条件的文件需要同步")


if __name__ == '__main__':
    main()

