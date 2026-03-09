from DrissionPage import ChromiumOptions, ChromiumPage
import json
import os
import shutil
import time
import requests

# ---------- 辅助函数 ----------
def read_cookie():
    """读取 cookie，优先从环境变量读取，其次从本地 tieba_cookies.json 文件读取（GitHub Secrets 推荐使用环境变量）"""
    if "TIEBA_COOKIES" in os.environ:
        try:
            cookies = json.loads(os.environ["TIEBA_COOKIES"])
            print("✅ 从环境变量加载 Cookie 成功")
            return cookies
        except json.JSONDecodeError:
            print("❌ 环境变量 Cookie 格式错误！")
    # 本地文件作为后备（仅用于测试，GitHub 上不建议存放敏感文件）
    cookie_file = "tieba_cookies.json"
    if os.path.exists(cookie_file):
        try:
            with open(cookie_file, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
                print("✅ 从本地文件加载 Cookie 成功")
                return cookies
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️ 读取本地 Cookie 文件失败：{e}")
    print("❌ 贴吧 Cookie 未配置（环境变量无效且本地文件不存在/错误）")
    return []

def wait_for_element(page, xpath, timeout=5, interval=0.2):
    """等待元素出现，返回元素或 None"""
    end = time.time() + timeout
    while time.time() < end:
        ele = page.ele(xpath)
        if ele:
            return ele
        time.sleep(interval)
    return None

def safe_get_text(element):
    """安全获取元素文本，避免异常"""
    return element.text if element else "未知"

def get_level_exp(page):
    """获取等级和经验，加入显式等待和更灵活的定位规则"""
    level = "未知"
    exp = "未知"

    # 等级定位（根据实际页面结构调整）
    level_ele = (wait_for_element(page, 'xpath://*[contains(text(), "级")]', timeout=3) or
                 wait_for_element(page, 'xpath://span[contains(@class, "level")]', timeout=2))
    if level_ele:
        level = level_ele.text.strip()

    # 经验定位
    exp_ele = (wait_for_element(page, 'xpath://*[contains(text(), "经验")]', timeout=3) or
               wait_for_element(page, 'xpath://span[contains(@class, "exp")]', timeout=2))
    if exp_ele:
        exp = exp_ele.text.strip()

    return level, exp

def safe_filename(name):
    """处理文件名中的非法字符"""
    illegal_chars = ['/', ':', '*', '?', '"', '<', '>', '|']
    for char in illegal_chars:
        name = name.replace(char, '_')
    return name[:50]

# ---------- 主程序 ----------
if __name__ == "__main__":
    print("🚀 程序开始运行（GitHub Actions 适配版）")
    start_time = time.time()
    notice = ''

    # 创建截图保存目录
    screenshot_dir = "tieba_screenshots"
    if not os.path.exists(screenshot_dir):
        os.makedirs(screenshot_dir)
        print(f"📁 已创建截图保存目录：{os.path.abspath(screenshot_dir)}")

    # ---------- 浏览器配置（GitHub 环境） ----------
    co = ChromiumOptions()
    co.headless()  # GitHub 必须无头模式
    co.set_argument('--blink-settings=imagesEnabled=false')
    co.set_argument('--disable-extensions')
    co.set_argument('--disable-notifications')
    co.set_argument('--disable-popup-blocking')
    co.set_argument('--no-sandbox')  # GitHub 环境需要
    co.set_argument('--disable-dev-shm-usage')  # 解决资源限制

    # 自动查找 Chrome 路径（GitHub 环境通常为 /usr/bin/google-chrome）
    chrome_path = shutil.which("google-chrome") or shutil.which("chrome")
    if chrome_path:
        co.set_browser_path(chrome_path)
        print(f"🌐 已设置浏览器路径：{chrome_path}")
    else:
        print("⚠️ 未找到 Chrome，将尝试使用默认路径")

    # 使用随机端口避免冲突（GitHub 环境可能同时运行多个实例）
    import random
    port = random.randint(9222, 9322)
    co.set_local_port(port)

    try:
        page = ChromiumPage(co)
    except Exception as e:
        print(f"❌ 浏览器启动失败：{e}")
        exit(1)

    # ---------- 登录 ----------
    url = "https://tieba.baidu.com/"
    page.get(url)
    cookies = read_cookie()
    if cookies:
        page.set.cookies(cookies)
    page.refresh()
    print("⏳ 等待登录完成...")
    if not wait_for_element(page, 'xpath://a[@id="nameValue"]', timeout=20):
        print("❌ 登录超时，请检查 Cookie 是否有效")
        page.save_screenshot(os.path.join(screenshot_dir, "login_failed.png"))
        page.close()
        exit()
    print("✅ 登录成功")

    # ---------- 签到主循环 ----------
    over = False
    yeshu = 0
    count = 0
    fail_list = []

    while not over:
        yeshu += 1
        page.get(f"https://tieba.baidu.com/i/i/forum?&pn={yeshu}")
        print(f"📄 正在加载第 {yeshu} 页...")
        table_xpath = 'xpath://*[@id="like_pagelet"]/div[1]/div[1]/table'
        if not wait_for_element(page, table_xpath, timeout=20):
            print(f"📄 第 {yeshu} 页无表格数据，结束翻页")
            over = True
            break
        print(f"✅ 第 {yeshu} 页加载成功")

        for i in range(2, 22):
            try:
                link_xpath = f'xpath://*[@id="like_pagelet"]/div[1]/div[1]/table/tbody/tr[{i}]/td[1]/a'
                link_elem = wait_for_element(page, link_xpath, timeout=3)
                if not link_elem:
                    print(f"  第 {i} 行无贴吧链接，可能已到本页末尾")
                    over = True
                    break
                tieba_url = link_elem.attr("href")
                name = link_elem.attr("title")
                if not tieba_url or not name:
                    continue
                print(f"\n▶ 正在处理第 {i-1} 个贴吧：{name}")
            except Exception as e:
                print(f"⚠️ 获取第 {i} 个贴吧链接异常：{e}，跳过")
                continue

            try:
                page.get(tieba_url)
                print(f"⏳ 进入贴吧，判断签到状态...")
                # 判断是否已签到：查找包含“连续”的span
                is_sign_ele = wait_for_element(page, 'xpath://*[@id="signstar_wrapper"]/a/span[1]', timeout=3)
                is_sign = safe_get_text(is_sign_ele)

                if is_sign.startswith("连续"):
                    msg = f"✅ {name}吧：已签到过！"
                    print(msg)
                    notice += msg + '\n\n'
                    count += 1
                    page.back()
                    wait_for_element(page, table_xpath, timeout=5)
                    print("--------------------------------------------------")
                    continue
                else:
                    # 未签到：点击签到按钮
                    sign_btn = page.ele('xpath://*[@id="signstar_wrapper"]/a[@title="签到"]')
                    if sign_btn:
                        sign_btn.click(2)  # 双击
                        print("⏳ 已点击签到，等待签到完成...")
                        # 等待按钮 title 变为“签到完成”
                        success_ele = wait_for_element(page, 'xpath://*[@id="signstar_wrapper"]/a[@title="签到完成"]',
                                                       timeout=8)
                        if success_ele:
                            time.sleep(0.5)
                            level, exp = get_level_exp(page)
                            msg = f"🎉 {name}吧：签到成功！等级：{level}，经验：{exp}"
                        else:
                            print("⏳ 等待超时，刷新页面...")
                            page.refresh()
                            if wait_for_element(page, 'xpath://*[@id="signstar_wrapper"]/a[@title="签到完成"]',
                                                timeout=5):
                                level, exp = get_level_exp(page)
                                msg = f"🎉 {name}吧：签到成功（刷新后）！等级：{level}，经验：{exp}"
                            else:
                                level, exp = "未知", "未知"
                                msg = f"⚠️ {name}吧：签到状态未知，当前等级：{level}，经验：{exp}"
                        print(msg)
                        notice += msg + '\n\n'
                    else:
                        msg = f"❓ {name}吧：未找到签到按钮"
                        print(msg)
                        safe_name = safe_filename(name)
                        screenshot_path = os.path.join(screenshot_dir, f"{safe_name}_no_sign_btn.png")
                        page.save_screenshot(screenshot_path)
                        print(f"📸 已保存截图：{os.path.abspath(screenshot_path)}")
                        notice += msg + f"\n（截图路径：{os.path.abspath(screenshot_path)}）\n\n"
                        fail_list.append(name)

                count += 1
                print("--------------------------------------------------")
                page.back()
                wait_for_element(page, table_xpath, timeout=5)

            except Exception as e:
                err_msg = f"⚠️ 处理 {name} 吧时出错：{str(e)}，已跳过"
                print(err_msg)
                safe_name = safe_filename(name)
                screenshot_path = os.path.join(screenshot_dir, f"{safe_name}_error.png")
                page.save_screenshot(screenshot_path)
                print(f"📸 已保存异常截图：{os.path.abspath(screenshot_path)}")
                notice += err_msg + f"\n（异常截图路径：{os.path.abspath(screenshot_path)}）\n\n"
                fail_list.append(name)
                count += 1
                print("--------------------------------------------------")
                try:
                    page.back()
                    wait_for_element(page, table_xpath, timeout=5)
                except:
                    page.get(f"https://tieba.baidu.com/i/i/forum?&pn={yeshu}")
                    wait_for_element(page, table_xpath, timeout=5)
                continue

    page.close()

    # ---------- 汇总结果 ----------
    end_time = time.time()
    total_time = round(end_time - start_time, 2)
    summary_msg = f"\n===== 签到汇总 ====="
    summary_msg += f"\n总耗时：{total_time} 秒"
    summary_msg += f"\n累计处理贴吧数：{count}"
    summary_msg += f"\n处理失败的贴吧：{fail_list if fail_list else '无'}"
    summary_msg += f"\n截图保存目录：{os.path.abspath(screenshot_dir)}（共 {len(os.listdir(screenshot_dir)) if os.path.exists(screenshot_dir) else 0} 张截图）"
    print(summary_msg)
    notice += summary_msg

    # ---------- Server酱推送 ----------
    if "SendKey" in os.environ:
        api = f'https://sctapi.ftqq.com/{os.environ["SendKey"]}.send'
        title = "贴吧签到信息（GitHub Actions版）"
        data = {"text": title, "desp": notice}
        try:
            resp = requests.post(api, data=data, timeout=30)
            if resp.status_code == 200:
                print("📧 Server酱通知发送成功")
            else:
                print(f"⚠️ Server酱通知失败，状态码：{resp.status_code}")
        except Exception as e:
            print(f"⚠️ 通知异常：{e}")
    else:
        print("📭 未配置Server酱")

    print("\n🏁 程序运行结束")
