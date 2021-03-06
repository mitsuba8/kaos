#-*- coding:utf-8 -*-
import re
import time
import math
import io
import codecs

# 每次注册使用 triggers 数量最大值
# 此限制源于 Google 拼音输入法扩展 API 参考指南
__MAX_REGISTER_TRIGGERS = 200

# 写入扩展文本中的生成器信息
GEN_INFO = """
---- 本文件由颜文字扩展生成器 kaos 自动生成
---- 项目地址: https://github.com/tisyang/kaos/
"""

# 生成器版本号
GEN_VERSION = "1.0"

# 写入扩展文本中的回调函数字符串
__CALLBACK_STR = """
function prefix_get_kaos(str)
    local t = prefix_dict[str]
    if not t then return str end
    if 'string' == type(t) then
        t = prefix_dict[t]
    end
    local len = #t
    if len > 1 then
        local index = math.random(len)
        return t[index]
    else
        return t[len]
    end
end

"""
def __get_callback_str(prefix):
    return __CALLBACK_STR.replace("prefix", "{0}".format(prefix))


# 词定义行匹配用的正则表达式
__PATTERN_LINE_WORDS = re.compile(r'''
    ([a-z]+)        # 拼音
    (?:\t+|\ {4,})  # TAB分隔/或者4个以上空格
    (.+)            # 颜文字
''', re.VERBOSE)

# 映射拼音行匹配用的正则表达式
__PATTERN_LINE_MAPPING = re.compile(r'''
    ([a-z]+)    # 拼音
    \s*         # 空白符
    :           # 冒号分隔符
    \s*         # 空白符
    ([a-z]+)    # 被映射拼音
''', re.VERBOSE)

def parse(filename):
    '''解析文件中的词定义
    参数:
        filename 为 utf-8 编码的词汇文件
    返回值:
        返回存储存储词的字典
        字典成员:
        字典键为 trigger 字符串
        字典值有两类:
            集合:   集合成员类型为 string, 即颜文字
                    集合所有定义了 trigger 对应的所有输出词集合
            字符串: 这表明这个 trigger 对另一个已有 trigger 的存在映射关系
    '''
    # 存储 词
    dic = {}
    with open(filename, mode="r", encoding="utf-8") as f:
        for line in f.readlines():
            # 忽略注释行
            if(line[0] == '#'):
                continue
            # 去掉首尾空白
            line = line.strip()
            # 忽略空白行
            if not line:
                continue
            # 先匹配词行定义
            match_word = __PATTERN_LINE_WORDS.match(line)
            if match_word:
                trigger, content = match_word.groups()
                assert trigger, "trigger string need"
                assert content, "content string need"
                # 如果字典键中已有 trigger
                if trigger in dic:
                    c = dic[trigger]
                    # 判断已存在的值的类型
                    # 如果是集合, 表明当前行定义了 trigger 对应的新词
                    # 加入这个新词到集合中
                    # 词定义为一个 string
                    if type(c) is set:
                        c.add(content)
                        continue
                    # 如果是字符串, 表明当前行定义的 trigger 对应的词
                    # 但是原有词库中此 trigger 映射了另外一个 trigger
                    # 存储新的词定义, 以前的映射定义不再有效
                    # 并输出警告
                    elif type(c) is str:
                        dic[trigger] = set()
                        dic[trigger].add(content)
                        print("warning: reduplicate trigger '{0}', old mapping will be replaced by a word '{1}'".format(trigger, line))
                        continue
                    # 如果是其它类型, 报错退出
                    else:
                        assert False, "error: wrong type of value in dic, the key is {0}".format(trigger)
                # 如果字典键中不存在 trigger
                else:
                    # 新建词定义
                    dic[trigger] = set()
                    dic[trigger].add(content)
                    continue
            # 匹配映射行定义
            match_mapping = __PATTERN_LINE_MAPPING.match(line)
            if match_mapping:
                trigger, mapping = match_mapping.groups()
                assert trigger, "trigger string need"
                assert mapping, "mapping string need"
                # 如果字典键中已有 trigger
                if trigger in dic:
                    # 判断已存在的值的类型
                    # 如果是集合, 则忽略当前行定义的映射关系
                    # 输出警告
                    c = dic[trigger]
                    if type(c) is set:
                        print("warning: reduplicate trigger '{0}', mapping '{1}' will be ignored.".format(trigger, line))
                        continue
                    # 如果是字符串, 则更新已有的映射关系
                    # 输出警告
                    elif type(c) is str:
                        if c != mapping:
                            dic[trigger] = mapping
                            print("warning: reduplicate trigger '{0}', old mapping will be replaced by a mapping '{1}'".format(trigger, line))
                        continue
                    # 如果是其他类型, 报错退出
                    else:
                        assert False, "error: wrong type of value in dic, the key is {0}".format(trigger)
                # 如果字典键中不存在 trigger
                else:
                    # 添加当前映射定义
                    dic[trigger] = mapping
                    continue
            # 前两个匹配都不成功
            # 警告信息
            print("warning: match failed in line '{0}'".format(line))
    return dic

def __serialize_triggers(triggers_list, triggers_name):
    '''将一系列 trigger 序列化为 lua 源代码
    '''
    output = io.StringIO()
    output.write('{0} = {{\n'.format(triggers_name))
    for trigger in triggers_list:
        output.write("\t'{0}',\n".format(trigger))
    output.write('}\n')
    res = output.getvalue()
    output.close()
    return res

def convert2lua(prefix, dic, filename, info, hintstr):
    '''转换词库定义为扩展文件
    参数:
        prefix: 由于谷歌拼音会把扩展中的符号都放入全局空间，所以需要一个独特
                前缀来避免不同扩展符号混淆
        dic: 解析的词库
        info: 扩展说明文字
        hintstr: 注册扩展时候的说明性文字

    '''
    with open(filename, mode='w', encoding="utf-8") as f:
        f.write('--coding:utf-8\n')
        # 写入扩展说明信息
        f.write(info)
        f.write('\n')
        f.write('-- 生成时间: {0}\n'.format(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())))
        f.write('-- 绑定词条数: {0}\n\n'.format(len(dic)))
        # 写入生成器信息
        f.write(GEN_INFO)
        # 写入版本以及修订信息
        f.write('---- 生成器版本: {0}\n\n'.format(GEN_VERSION))
        f.write('\n\n')
        f.write('{0}_dict = {{\n'.format(prefix))
        # 顺序遍历词库
        triggers = list(dic.keys())
        triggers.sort()
        for key in triggers:
            # 处理字典值是 集合的情况
            if type(dic[key]) is set:
                f.write('\n\t["{0}"] = {{\n'.format(key))
                # 依次编码
                # 排序
                lst = list(dic[key])
                lst.sort()
                for word in lst:
                    f.write('\t\t[==[{0}]==],\n'.format(word))
                f.write('\t},\n')
            # 字典值是 字符串的情况
            elif type(dic[key]) is str:
                f.write('\n\t["{0}"] = "{1}",\n'.format(key, dic[key]))
            # 字典值是其他类型, 报错
            else:
                assert False, "error: wrong type of value in dic, the key is {0}".format(key)
        f.write('}\n')

        # 分割 triggers
        # 每组 triggers 不超过 MAX_REGISTER_TRIGGERS
        count = len(triggers)
        groups_count = math.ceil(count / __MAX_REGISTER_TRIGGERS)
        groups = []
        for i in range(groups_count):
            triggers_name = "{0}_triggers_{1}".format(prefix, i)
            start = i * __MAX_REGISTER_TRIGGERS
            end = start + __MAX_REGISTER_TRIGGERS
            triggers_list = triggers[start:end]
            triggers_str = __serialize_triggers(triggers_list, triggers_name)
            f.write(triggers_str)
            f.write('\n')
            groups.append(triggers_name)

        # 写入回调函数
        f.write(__get_callback_str(prefix))
        # 写入注册函数
        # 写入随机种子发生器函数
        f.write('math.randomseed(os.time())\n')
        # 依次注册
        for triggers_name in groups:
            f.write('ime.register_trigger("{0}_get_kaos", \"{1}\", {2}, {{}})\n'.format(prefix, hintstr, triggers_name))
