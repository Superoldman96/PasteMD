-- html-md-math.lua
-- 专门用于 HTML+MD 工作流的公式处理
-- 将数学公式输出为 HTML 段落包裹的 $...$ 格式
-- 例如: <p>$x^2$</p> (行内) 或 <p>$$x^2$$</p> (块级)

-- 简单的空白规范化
local function normalize_tex(s)
  s = s:gsub("^%s+", ""):gsub("%s+$", "")
  s = s:gsub("%s+", " ")
  return s
end

-- 将数学元素转换为 RawInline HTML
local function math_to_html(el)
  local open_delim, close_delim
  
  if el.mathtype == "DisplayMath" then
    -- 块公式：用 $$ 包裹，放在单独的 <p> 中
    open_delim, close_delim = "$$", "$$"
  else
    -- 行内公式：用 $ 包裹
    open_delim, close_delim = "$", "$"
  end
  
  local content = normalize_tex(el.text)
  local formula = open_delim .. content .. close_delim
  
  -- 返回 RawInline HTML，保持在文本流中
  return pandoc.RawInline("html", formula)
end

return {
  {
    Math = math_to_html
  }
}
