# -*- coding: utf-8 -*-
"""HTML+Markdown paste workflow for note-taking apps."""

import os
import subprocess
import re

from .extensible_base import ExtensibleWorkflow
from ....core.errors import ClipboardError, PandocError
from ....utils.clipboard import (
    get_clipboard_html,
    get_clipboard_text,
    is_clipboard_empty,
    set_clipboard_rich_text,
    simulate_paste,
)
from ....utils.html_analyzer import is_plain_html_fragment
from ....config.paths import resource_path
from ....i18n import t


# 获取 HTML+MD 专用 Lua 过滤器路径
LUA_HTML_MD_MATH = resource_path("lua/html-md-math.lua")
if not os.path.isfile(LUA_HTML_MD_MATH):
    LUA_HTML_MD_MATH = resource_path("pastemd/lua/html-md-math.lua")


class HtmlWorkflow(ExtensibleWorkflow):
    """HTML 粘贴工作流
    
    适用于 Notion、语雀等笔记软件：
    - 读取剪贴板 HTML/Markdown
    - 转换为 Markdown
    - 再转换为纯净 HTML（公式可保持 $...$ 格式）
    - 同时设置剪贴板的 HTML 和纯文本格式
    - 模拟粘贴
    """
    
    @property
    def workflow_key(self) -> str:
        return "html"
    
    def execute(self) -> None:
        """执行 HTML+MD 粘贴工作流"""
        try:
            # 1. 读取剪贴板内容
            content_type, content = self._read_clipboard()
            self._log(f"HTML+MD workflow: content_type={content_type}")
            
            # 2. 转换为 Markdown（如果是 HTML）
            if content_type == "html":
                md_text = self.doc_generator.convert_html_to_markdown_text(
                    content, self.config
                )
            else:
                md_text = content
            
            # 3. 预处理 Markdown
            md_text = self.markdown_preprocessor.process(md_text, self.config)
            
            # 4. 转换为纯净 HTML（使用专用方法）
            keep_formula = self.workflow_config.get("keep_formula_latex", True)
            html_text = self._convert_md_to_html_for_notes(md_text, keep_formula)
            print(f"Converted HTML:\n{html_text}\n--- End of HTML ---")
            # 5. 设置剪贴板（HTML + 纯文本 Markdown）
            set_clipboard_rich_text(html=html_text, text=md_text)
            self._log("Set clipboard with HTML and plain text")
            
            # 6. 模拟粘贴
            simulate_paste()
            
            # 7. 通知成功
            self._notify_success(t("workflow.html_md.paste_success"))
            
        except ClipboardError as e:
            self._log(f"Clipboard error: {e}")
            self._notify_error(t("workflow.clipboard.read_failed"))
        except PandocError as e:
            self._log(f"Pandoc error: {e}")
            self._notify_error(t("workflow.html.convert_failed_generic"))
        except Exception as e:
            self._log(f"HTML+MD workflow failed: {e}")
            import traceback
            traceback.print_exc()
            self._notify_error(t("workflow.generic.failure"))
    
    def _read_clipboard(self) -> tuple[str, str]:
        """读取剪贴板内容，返回 (类型, 内容)"""
        # 优先尝试 HTML
        try:
            html = get_clipboard_html(self.config)
            if not is_plain_html_fragment(html):
                return ("html", html)
        except ClipboardError:
            pass
        
        # 尝试纯文本
        if not is_clipboard_empty():
            return ("markdown", get_clipboard_text())
        
        raise ClipboardError("剪贴板为空或无有效内容")
    
    def _convert_md_to_html_for_notes(self, md_text: str, keep_formula: bool = True) -> str:
        """
        转换 Markdown 为笔记软件适用的 HTML
        
        使用专用 Lua 过滤器 html-md-math.lua：
        - 保持公式为 $...$ / $$...$$ 格式
        - 输出纯净的 HTML fragment
        """
        pandoc_path = self.config.get("pandoc_path", "pandoc")
        
        cmd = [
            pandoc_path,
            "-f", "markdown+tex_math_dollars+raw_tex+tex_math_double_backslash+tex_math_single_backslash",
            "-t", "html",
            "-o", "-",
            "--wrap", "none",
        ]
        
        # 使用专用公式过滤器（保持 $...$ 格式）
        if keep_formula and os.path.isfile(LUA_HTML_MD_MATH):
            cmd += ["--lua-filter", LUA_HTML_MD_MATH]
        
        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW
        
        result = subprocess.run(
            cmd,
            input=md_text.encode("utf-8"),
            capture_output=True,
            text=False,
            shell=False,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        
        if result.returncode != 0:
            err = (result.stderr or b"").decode("utf-8", "ignore")
            self._log(f"Pandoc MD to HTML error: {err}")
            raise PandocError(err or "Pandoc Markdown to HTML conversion failed")
        
        html = result.stdout.decode("utf-8", "ignore")
        return self._strip_html_wrapper(html)
    
    def _strip_html_wrapper(self, html: str) -> str:
        """移除 Pandoc 生成的 HTML 包装标签（如 DOCTYPE、html、body）"""
        # 尝试提取 body 内容
        body_match = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
        if body_match:
            return body_match.group(1).strip()
        
        # 移除 DOCTYPE 和 html/head 标签
        html = re.sub(r"<!DOCTYPE[^>]*>", "", html, flags=re.IGNORECASE)
        html = re.sub(r"<html[^>]*>|</html>", "", html, flags=re.IGNORECASE)
        html = re.sub(r"<head[^>]*>.*?</head>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<body[^>]*>|</body>", "", html, flags=re.IGNORECASE)
        
        return html.strip()

