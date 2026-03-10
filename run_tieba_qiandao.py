from DrissionPage import ChromiumOptions, ChromiumPage
import json
import os
import time
import requests
import random

# ---------- 辅助函数 ----------
def read_cookie():
    """读取 cookie，优先从环境变量读取（GitHub Secrets 方式）"""
    if "TIEBA_COOKIES" in os.environ:
        try:
            cookies = json.loads(os.environ["TIEBA_COOKIES"])
            print("✅ 从环境变量加载 Cookie 成功")
            return cookies
        except json.JSONDecodeError:
            print("❌ 环境变量 Cookie 格式错误！")
    else:
        print("❌ 未找到 TIEBA_COOKIES 环境变量")
    return []

def safe_get_text(element):
    """安全获取元素文本"""
    return element.text if element else "未知"

def safe_filename(name):
    """处理文件名中的非法字符"""
    illegal_chars = ['/', ':', '*', '?', '"', '<', '>', '|']
    for char in illegal_chars:
        name = name.replace(char, '_')
    return name[:50]

# ---------- 主程序 ----------
if __name__ == "__main__":
    print("🚀 GitHub Actions 版贴吧签到脚本启动")
    start_time = time.time()
    notice = ''

    # 截图保存目录（GitHub 工作区）
    screenshot_dir = "tieba_screenshots"
    if not os.path.exists(screenshot_dir):
        os.makedirs(screenshot_dir)
        print(f"📁 创建截图目录：{screenshot_dir}")

    # ---------- 浏览器配置（GitHub 环境关键配置） ----------
    co = ChromiumOptions()
    co.headless(True)                     # 必须无头模式
    co.set_argument('--blink-settings=imagesEnabled=false')
    co.set_argument('--disable-extensions')
    co.set_argument('--disable-notifications')
    co.set_argument('--disable-popup-blocking')
    co.set_argument('--no-sandbox')        # 解决权限问题
    co.set_argument('--disable-dev-shm-usage')  # 解决内存问题

    # GitHub 环境中 Chrome 通常位于 /usr/bin/google-chrome
    chrome_path = "/usr/bin/google-chrome"
    if os.path.exists(chrome_path):
        co.set_browser_path(chrome_path)
        print(f"🌐 设置浏览器路径：{chrome_path}")
    else:
        print("⚠️ 未找到指定 Chrome，将尝试自动查找")

    # 随机端口避免多个实例冲突（GitHub 中一般不需要，但无害）
    port = random.randint(9222, 9322)
    co.set_local_port(port)

    try:
        page = ChromiumPage(co)
    except Exception as e:
        print(f"❌ 浏览器启动失败：{e}")
        exit(1)

    # ---------- 登录 ----------
    page.get("https://tieba.baidu.com/")
    cookies = read_cookie()
    if cookies:
        page.set.cookies(cookies)
    page.refresh()
    print("⏳ 等待登录完成...")

    # 检查登录状态
    if not page.ele('xpath://a[@id="nameValue"]', timeout=20):
        print("❌ 登录超时，请检查 Cookie 是否有效")
        page.save_screenshot(os.path.join(screenshot_dir, "login_failed.png"))
        page.close()
        exit(1)

    print("✅ 登录成功")

    # ---------- 签到主循环 ----------
    over = False
    yeshu = 0
    count = 0
    fail_list = []

    while not over:
        yeshu += 1
        page.get(f"https://tieba.baidu.com/i/i/forum?&pn={yeshu}")
        print(f"\n📄 加载第 {yeshu} 页列表...")

        table_xpath = 'xpath://*[@id="like_pagelet"]/div[1]/div[1]/table'
        if not page.ele(table_xpath, timeout=10):
            print(f"📄 第 {yeshu} 页无数据，翻页结束")
            over = True
            break

        # 提取本页所有贴吧链接
        tieba_list = []
        links = page.eles('xpath://*[@id="like_pagelet"]/div[1]/div[1]/table/tbody/tr/td[1]/a')
        if not links:
            print("本页无贴吧链接，翻页结束")
            over = True
            break

        for link in links:
            t_url = link.attr("href")
            t_name = link.attr("title")
            if t_url and t_name:
                if not t_url.startswith("http"):
                    t_url = f"https://tieba.baidu.com{t_url}"
                tieba_list.append((t_name, t_url))

        print(f"🔍 本页共 {len(tieba_list)} 个贴吧")

        for name, tieba_url in tieba_list:
            print(f"\n▶ 处理：{name}吧")
            try:
                page.get(tieba_url)
                print("⏳ 判断签到状态...")

                # 是否已签到
                is_sign_ele = page.ele('xpath://*[@id="signstar_wrapper"]/a/span[1]', timeout=3)
                is_sign = safe_get_text(is_sign_ele)
                if is_sign.startswith("连续"):
                    msg = f"✅ {name}吧：已签到过"
                    print(msg)
                    notice += msg + '\n'
                    count += 1
                    continue

                # 未签到，点击签到（双击）
                sign_btn = page.ele('xpath://*[@id="signstar_wrapper"]/a[@title="签到"]', timeout=3)
                if sign_btn:
                    sign_btn.click(2)  # 双击
                    print("⏳ 等待签到完成...")
                    # 等待按钮 title 变为“签到完成”
                    success_ele = page.ele('xpath://*[@id="signstar_wrapper"]/a[@title="签到完成"]', timeout=8)
                    if success_ele:
                        msg = f"🎉 {name}吧：签到成功"
                    else:
                        print("⏳ 超时，刷新页面确认...")
                        page.refresh()
                        if page.ele('xpath://*[@id="signstar_wrapper"]/a[@title="签到完成"]', timeout=5):
                            msg = f"🎉 {name}吧：签到成功（刷新后确认）"
                        else:
                            msg = f"⚠️ {name}吧：签到状态未知"
                    print(msg)
                    notice += msg + '\n\n'
                else:
                    msg = f"❓ {name}吧：未找到签到按钮"
                    print(msg)
                    safe_name = safe_filename(name)
                    screenshot_path = os.path.join(screenshot_dir, f"{safe_name}_no_sign_btn.png")
                    page.save_screenshot(screenshot_path)
                    notice += msg + f" (截图: {safe_name}_no_sign_btn.png)\n"
                    fail_list.append(name)

                count += 1

            except Exception as e:
                err_msg = f"⚠️ 处理 {name} 吧出错：{str(e)}，已跳过"
                print(err_msg)
                safe_name = safe_filename(name)
                screenshot_path = os.path.join(screenshot_dir, f"{safe_name}_error.png")
                page.save_screenshot(screenshot_path)
                notice += err_msg + f" (截图: {safe_name}_error.png)\n"
                fail_list.append(name)
                count += 1
                continue

    page.close()

    # ---------- 汇总 ----------
    end_time = time.time()
    total_time = round(end_time - start_time, 2)
    summary = f"\n===== 签到汇总 =====\n"
    summary += f"总耗时：{total_time} 秒\n"
    summary += f"累计处理：{count} 个吧\n"
    summary += f"失败列表：{fail_list if fail_list else '无'}\n"
    summary += f"截图目录：{screenshot_dir}"
    print(summary)
    notice += '\n' + summary

    # ---------- Server酱推送 ----------
    # ---------- Server酱推送 ----------
    if "SendKey" in os.environ:  # 与你的环境变量名一致
        api = f'https://sctapi.ftqq.com/{os.environ["SendKey"]}.send'
        title = "贴吧签到报告"
        data = {"title": title, "desp": notice}
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            resp = requests.post(api, data=data, headers=headers, timeout=30)
            if resp.status_code == 200:
                result = resp.json()
                if result.get("code") == 0:
                    print("✅ 推送成功")
                else:
                    print(f"❌ 推送失败，错误码：{result.get('code')}，消息：{result.get('message')}")
            else:
                print(f"❌ HTTP 错误：{resp.status_code}")
                print(resp.text)
        except Exception as e:
            print(f"❌ 推送异常：{e}")
    else:
        print("📭 未配置 SendKey，跳过推送")
