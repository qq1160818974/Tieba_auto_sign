from DrissionPage import ChromiumOptions, ChromiumPage
import json
import os
import shutil
import time
import requests

# ---------- 辅助函数 ----------
def read_cookie():
    """读取 cookie，优先从环境变量读取，其次从本地 tieba_cookies.json 文件读取"""
    if "TIEBA_COOKIES" in os.environ:
        try:
            cookies = json.loads(os.environ["TIEBA_COOKIES"])
            print("✅ 从环境变量加载 Cookie 成功")
            return cookies
        except json.JSONDecodeError:
            print("❌ 环境变量 Cookie 格式错误！")
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
    """获取等级和经验，如果找不到返回'未知'（兼容新旧版）"""
    level = "未知"
    exp = "未知"
    # 等级定位
    level_ele = (page.ele('xpath://div[contains(@class, "user-level")]/span[1]') or
                 page.ele('xpath://*[@id="pagelet_aside/pagelet/my_tieba"]/div/div[1]/div[3]/div[1]/a/div[2]'))
    if level_ele:
        level = level_ele.text.strip()
    # 经验定位
    exp_ele = (page.ele('xpath://div[contains(@class, "user-exp")]/span[1]') or
               page.ele('xpath://*[@id="pagelet_aside/pagelet/my_tieba"]/div/div[1]/div[3]/div[2]/a/div[2]/span[1]'))
    if exp_ele:
        exp = exp_ele.text.strip()
    return level, exp

# ---------- 主程序 ----------
if __name__ == "__main__":
    print("🚀 程序开始运行（快速跳过已签到版）")
    start_time = time.time()
    notice = ''

    # ---------- 浏览器配置 ----------
    co = ChromiumOptions()
    co.headless()  # 启用无头模式
    co.set_argument('--blink-settings=imagesEnabled=false')
    co.set_argument('--disable-extensions')
    co.set_argument('--disable-notifications')
    co.set_argument('--disable-popup-blocking')
    chromium_path = shutil.which("chromium-browser") or shutil.which("chrome") or shutil.which("google-chrome")
    if chromium_path:
        co.set_browser_path(chromium_path)

    page = ChromiumPage(co)

    # ---------- 登录 ----------
    url = "https://tieba.baidu.com/"
    page.get(url)
    cookies = read_cookie()
    if cookies:
        page.set.cookies(cookies)
    page.refresh()
    if not wait_for_element(page, 'xpath://a[@id="nameValue"]', timeout=15):
        print("❌ 登录超时，请检查 Cookie 是否有效")
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
        if not wait_for_element(page, 'xpath://*[@id="like_pagelet"]/div[1]/div[1]/table', timeout=10):
            print(f"📄 第 {yeshu} 页无数据，结束翻页")
            over = True
            break

        for i in range(2, 22):
            try:
                link_xpath = f'xpath://*[@id="like_pagelet"]/div[1]/div[1]/table/tbody/tr[{i}]/td[1]/a'
                link_elem = wait_for_element(page, link_xpath, timeout=3)
                if not link_elem:
                    print(f"  第 {i} 行无贴吧链接，认为已到本页末尾")
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

            # ---------- 处理单个贴吧签到 ----------
            try:
                page.get(tieba_url)
                # 快速判断是否已签到（超时2秒）
                is_sign_ele = wait_for_element(page, 'xpath://*[@id="signstar_wrapper"]/a/span[1]', timeout=2)
                is_sign = safe_get_text(is_sign_ele)

                if is_sign.startswith("连续"):
                    # 已签到：立即返回，跳过等级经验获取
                    msg = f"✅ {name}吧：已签到过！"
                    print(msg)
                    notice += msg + '\n\n'
                    count += 1
                    page.back()
                    wait_for_element(page, 'xpath://*[@id="like_pagelet"]/div[1]/div[1]/table', timeout=5)
                    print("--------------------------------------------------")
                    continue
                else:
                    # 未签到：尝试点击签到按钮（双击）
                    sign_btn = (page.ele('xpath://a[contains(@class, "sign-btn") and contains(text(), "签到")]') or
                                page.ele('xpath://button[contains(@class, "sign-btn")]') or
                                page.ele('xpath://a[@class="j_signbtn sign_btn_bright j_cansign"]'))
                    if sign_btn:
                        sign_btn.click(2)  # 双击
                        # 等待签到成功（延长超时到8秒）
                        success_ele = wait_for_element(page, 'xpath://*[@id="signstar_wrapper"]/a/span[1][contains(text(), "连续")]', timeout=8)
                        if success_ele:
                            level, exp = get_level_exp(page)
                            msg = f"🎉 {name}吧：签到成功！等级：{level}，经验：{exp}"
                        else:
                            # 超时后刷新页面，再等待元素出现
                            page.refresh()
                            # 刷新后等待签到状态元素（不限定“连续”文本，因为可能已出现）
                            if wait_for_element(page, 'xpath://*[@id="signstar_wrapper"]/a/span[1]', timeout=5):
                                level, exp = get_level_exp(page)
                                msg = f"🎉 {name}吧：签到成功（刷新后）！等级：{level}，经验：{exp}"
                            else:
                                level, exp = "未知", "未知"
                                msg = f"⚠️ {name}吧：签到状态未知，当前等级：{level}，经验：{exp}"
                        print(msg)
                        notice += msg + '\n\n'
                    else:
                        msg = f"❓ {name}吧：未找到签到按钮（可能已无签到功能）"
                        print(msg)
                        notice += msg + '\n\n'
                        fail_list.append(name)

                count += 1
                print("--------------------------------------------------")
                page.back()
                wait_for_element(page, 'xpath://*[@id="like_pagelet"]/div[1]/div[1]/table', timeout=3)

            except Exception as e:
                err_msg = f"⚠️ 处理 {name} 吧时出错：{str(e)}，已跳过"
                print(err_msg)
                notice += err_msg + '\n\n'
                fail_list.append(name)
                count += 1
                print("--------------------------------------------------")
                try:
                    page.back()
                    wait_for_element(page, 'xpath://*[@id="like_pagelet"]/div[1]/div[1]/table', timeout=5)
                except:
                    page.get(f"https://tieba.baidu.com/i/i/forum?&pn={yeshu}")
                    wait_for_element(page, 'xpath://*[@id="like_pagelet"]/div[1]/div[1]/table', timeout=5)
                continue

    page.close()

    # ---------- 汇总结果 ----------
    end_time = time.time()
    total_time = round(end_time - start_time, 2)
    summary_msg = f"\n===== 签到汇总 ====="
    summary_msg += f"\n总耗时：{total_time} 秒"
    summary_msg += f"\n累计处理贴吧数：{count}"
    summary_msg += f"\n处理失败的贴吧：{fail_list if fail_list else '无'}"
    print(summary_msg)
    notice += summary_msg

    # ---------- Server酱推送 ----------
    if "SendKey" in os.environ:
        api = f'https://sc.ftqq.com/{os.environ["SendKey"]}.send'
        title = "贴吧签到信息（快速跳过）"
        data = {"text": title, "desp": notice}
        try:
            requests.post(api, data=data, timeout=30)
            print("📧 Server酱通知发送成功")
        except Exception as e:
            print(f"通知异常：{e}")
    else:
        print("📭 未配置Server酱")

    print("\n🏁 程序运行结束")
