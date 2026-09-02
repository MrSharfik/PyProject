import re, time, subprocess, os, difflib, string
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import (NoSuchWindowException, WebDriverException, NoSuchElementException,
                                        TimeoutException, ElementClickInterceptedException, StaleElementReferenceException)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

CHROME_DIR = r"C:\Users\user\Desktop\test\GoogleChromePortable64"
CHROME_EXE, DBG_PORT, INIT_URL = "GoogleChromePortable.exe", "9222", "https://nmfo-spo.edu.rosminzdrav.ru/#/user-account/my-plan"
ANS_PREFIX, Q_SIM_THR, A_SIM_THR = "Тест с ответами по теме", 0.80, 0.85

S = {
    "q_txt": (By.CSS_SELECTOR, "div.question-title-text"), "q_type": (By.CSS_SELECTOR, "div.mat-card-question__type"),
    "r_grp": (By.CSS_SELECTOR, "mat-radio-group.radio-group_answer"), "r_opt": (By.TAG_NAME, "mat-radio-button"),
    "c_grp": (By.CSS_SELECTOR, "span.checkbox-group_answer"), "c_opt": (By.CSS_SELECTOR, "mat-list-item.checkbox-button_answer"),
    "lbl": (By.CSS_SELECTOR, "span.question-inner-html-text"), "r_inp": (By.CSS_SELECTOR, "input[type='radio']"),
    "c_inp": (By.CSS_SELECTOR, "input[type='checkbox']"),
    "next_btn": (By.XPATH, "//button[contains(@class, 'question-buttons-primary') and .//span[contains(normalize-space(.), 'Следующий вопрос')]]")
}
q_tab_h, a_tab_h, ans_cache = None, None, None
P_TRANSLATOR = str.maketrans('', '', string.punctuation.replace('-', ''))

def _l(p, m): print(f"[{p}] {m}")
_li = lambda m: _l("I", m); _lw = lambda m: _l("W", m); _le = lambda m: _l("E", m); _lc = lambda m: _l("C!", m)
norm_text = lambda t: ' '.join(t.lower().translate(P_TRANSLATOR).split()) if t else ""

def launch_chrome(port):
    exe_p = os.path.join(CHROME_DIR, CHROME_EXE)
    if not os.path.exists(exe_p): _lc(f"{CHROME_EXE} не в {CHROME_DIR}"); return
    _li(f"Запуск Chrome, порт {port}...")
    try: return subprocess.Popen([exe_p, f"--remote-debugging-port={port}"], cwd=CHROME_DIR, creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e: _lc(f"Запуск Chrome: {e}")

def setup_driver(port):
    _li("Подключение...")
    opts = webdriver.ChromeOptions(); opts.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
    try:
        d = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=opts)
        _ = d.window_handles; _li("Успешно."); return d
    except WebDriverException as e:
         _li(f"Нет подключения. Порт {port} не активен") if any(s in str(e).lower() for s in ["cannot connect", "disconnected"]) else _le(f"setup_driver: {e}")
    except Exception as e: _le(f"setup_driver: {e}")

def id_tabs(d):
    global q_tab_h, a_tab_h
    try: handles = d.window_handles
    except WebDriverException: _le("Нет доступа к вкладкам."); return False
    if len(handles) < 2: _lw(f"Нужно 2 вкладки: тест и '{ANS_PREFIX}'."); return False
    
    temp_a_h = None
    for h_ in handles:
        try:
            d.switch_to.window(h_)
            if d.title.startswith(ANS_PREFIX): temp_a_h = h_; break
        except (NoSuchWindowException, WebDriverException): continue
    if not temp_a_h: _le(f"Вкладка ответов '{ANS_PREFIX}' не найдена."); return False

    temp_q_h = next((h_ for h_ in handles if h_ != temp_a_h), None)
            
    if temp_a_h and temp_q_h:
        a_tab_h, q_tab_h = temp_a_h, temp_q_h
        try: d.switch_to.window(q_tab_h)
        except (NoSuchWindowException, WebDriverException): _le("Не удалось переключиться на вкладку теста."); return False
        _li("Вкладки определены."); return True
    _le("Не удалось идентиф. вкладки (ответ найден, вопрос - нет)."); return False

get_lines = lambda d: [ln.strip() for ln in d.execute_script("return document.body.innerText").splitlines() if ln.strip()] \
                      if d else (_le("Чтение текста: нет драйвера"), [])[1]

def find_match_idx(target, lines_list, threshold):
    target_n, matches = norm_text(target), []
    for i, line in enumerate(lines_list):
        if line_n := norm_text(line):
            matches.append((i, difflib.SequenceMatcher(None, target_n, line_n).ratio()))
    if not matches: return
    best_i, hi_sim = max(matches, key=lambda item: item[1])
    return best_i if hi_sim >= threshold else None

def find_ans_text(page_lines, q_idx):
    if q_idx is None or q_idx >= len(page_lines) -1: return
    ans_l = [re.sub(r"^\s*\d+\)\s*", "", ln)[:-1].strip().rstrip(';.,')
             for i in range(q_idx + 1, min(q_idx + 10, len(page_lines)))
             if (ln := page_lines[i]).endswith('+') and re.match(r"^\s*\d+\)", ln)]
    return [a for a in ans_l if a] or None

def get_quiz_data(d):
    try:
        w = WebDriverWait(d, 7)
        q_el = w.until(EC.visibility_of_element_located(S["q_txt"]))
        q_text = q_el.text.strip()
        if not q_text: return None, [], "unknown"
        
        q_type_text = ""
        try: q_type_text = d.find_element(*S["q_type"]).text.lower()
        except NoSuchElementException: pass
        is_cb = "несколько" in q_type_text or "multiple" in q_type_text
        q_type = "checkbox" if is_cb else "radio"
        
        cfg = {"grp": S["c_grp" if is_cb else "r_grp"], "opt": S["c_opt" if is_cb else "r_opt"], 
               "inp": S["c_inp" if is_cb else "r_inp"]}
        
        grp_cont = w.until(EC.presence_of_element_located(cfg["grp"]))
        opt_els, ans_opts = grp_cont.find_elements(*cfg["opt"]), []
        for item_el in opt_els:
            try:
                main_el = item_el.find_element(By.TAG_NAME, "mat-checkbox") if is_cb else item_el
                txt_el = main_el.find_element(*S["lbl"])
                opt_text = txt_el.text.strip()
                inp_el = main_el.find_element(*cfg["inp"])
                clk_el = main_el 
                if not is_cb:
                    try: clk_el = txt_el.find_element(By.XPATH, "./ancestor::label[1]")
                    except NoSuchElementException: pass 
                if opt_text: ans_opts.append({"text": opt_text, "clk": clk_el, "inp": inp_el})
            except NoSuchElementException: continue 
        return q_text, ans_opts, q_type
    except TimeoutException: return None, [], "unknown"
    except Exception as e: _le(f"get_quiz_data: {e}"); return None, [], "unknown"

def _safe_click(d, el, w_sh):
    try:
        d.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});", el)
        w_sh.until(EC.element_to_be_clickable(el)); el.click(); return True
    except ElementClickInterceptedException:
        try: d.execute_script("arguments[0].click();", el); return True
        except: return False
    except: return False

def sel_answer(d, quiz_opts, corr_ans, q_type):
    if not corr_ans or not quiz_opts: return 0 if q_type == "checkbox" else False
    targets_n = [norm_text(t) for t in (corr_ans if isinstance(corr_ans, list) else [str(corr_ans)]) if t]
    if not targets_n: return 0 if q_type == "checkbox" else False
    w_sh = WebDriverWait(d, 2)
    
    if q_type == "radio":
        target_n, best_opt, hi_sim = targets_n[0], None, -1.0
        for opt in quiz_opts:
            if (sim := difflib.SequenceMatcher(None, target_n, norm_text(opt['text'])).ratio()) > hi_sim: hi_sim, best_opt = sim, opt
        if best_opt and hi_sim >= A_SIM_THR:
            try: is_sel = best_opt['inp'] and best_opt['inp'].is_selected()
            except (StaleElementReferenceException, WebDriverException) : is_sel = False
            return True if is_sel else _safe_click(d, best_opt['clk'], w_sh)
        return False
    
    sel_count = 0 # Checkbox logic
    for target_n in targets_n:
        best_opt_cb, hi_sim_cb = None, -1.0
        for opt in quiz_opts:
            if (sim := difflib.SequenceMatcher(None, target_n, norm_text(opt['text'])).ratio()) > hi_sim_cb: hi_sim_cb, best_opt_cb = sim, opt
        if best_opt_cb and hi_sim_cb >= A_SIM_THR:
            try: is_sel_cb = best_opt_cb['inp'] and best_opt_cb['inp'].is_selected()
            except (StaleElementReferenceException, WebDriverException): is_sel_cb = False
            if is_sel_cb: sel_count +=1; continue
            if _safe_click(d, best_opt_cb['clk'], w_sh): sel_count +=1
    return sel_count

def click_next(d):
    try:
        next_b = WebDriverWait(d,3).until(EC.element_to_be_clickable(S["next_btn"]))
        d.execute_script("arguments[0].click();", next_b); return True
    except TimeoutException: _li("Кнопка 'Далее' не найдена. Конец."); return False
    except Exception as e: _le(f"Клик 'Далее': {e}"); return False

def run_quiz(d):
    global q_tab_h, a_tab_h, ans_cache
    if not id_tabs(d): return False
    if a_tab_h:
        try:
            d.switch_to.window(a_tab_h); _li("Чтение ответов...")
            if not (ans_cache := get_lines(d)): _lw("Не удалось считать текст ответов.")
            d.switch_to.window(q_tab_h)
        except (NoSuchWindowException, WebDriverException) as e:
             _lc("Вкладка ответов закрыта или недоступна!") if isinstance(e, NoSuchWindowException) else _le(f"Кэширование ответов: {e}")
             return False
    else: _lw("Вкладка ответов не определена.")
    
    q_cnt, max_q = 0, 200
    _li("Начало теста...")
    while q_cnt < max_q:
        q_cnt += 1
        try:
            if d.current_window_handle != q_tab_h: d.switch_to.window(q_tab_h)
        except (NoSuchWindowException, WebDriverException): _lc("Вкладка теста закрыта!"); return True
        
        q_text, q_opts, q_type = get_quiz_data(d)
        if not q_text: _li(f"Вопрос {q_cnt}: Текст не найден. Конец?"); break
        
        found_ans = None
        if ans_cache and (q_idx := find_match_idx(q_text, ans_cache, Q_SIM_THR)) is not None:
            found_ans = find_ans_text(ans_cache, q_idx)
        
        try:
            if d.current_window_handle != q_tab_h: d.switch_to.window(q_tab_h)
        except (NoSuchWindowException, WebDriverException): _lc("Вкладка теста закрыта во время вопроса!"); return True

        if found_ans:
            if q_type == "checkbox":
                num_target = len(found_ans)
                sel_now_final = 0
                for attempt in range(num_target + 2): 
                    curr_q_txt, curr_q_opts, _ = get_quiz_data(d)
                    if not curr_q_txt or not curr_q_opts: _lw(f"ЧБ Повтор: Вопр/Ответы исчезли для {q_text[:20]}..."); break
                    
                    sel_answer(d, curr_q_opts, found_ans, q_type)
                    
                    sel_now = 0
                    norm_targets_cb = [norm_text(t) for t in found_ans if t]
                    for opt_item in curr_q_opts:
                        try:
                            if opt_item['inp'] and opt_item['inp'].is_selected() and \
                               any(difflib.SequenceMatcher(None, t_n, norm_text(opt_item['text'])).ratio() >= A_SIM_THR for t_n in norm_targets_cb):
                                sel_now +=1
                        except (StaleElementReferenceException, WebDriverException): pass
                    sel_now_final = sel_now
                    if sel_now >= num_target: break
                else:
                     _lw(f"ЧБ Макс.попыток для {q_text[:20]}. Выбр: {sel_now_final}/{num_target}")
            else: sel_answer(d, q_opts, found_ans, q_type)
        else: _li(f"Ответ на {q_cnt} ('{q_text[:20]}...') не найден.")
        if not click_next(d): break
    if q_cnt >= max_q: _lw(f"\nЛимит {max_q} вопросов.")
    return True

if __name__ == "__main__":
    chrome_p, drv = None, None
    launched_new = False
    try:
        drv = setup_driver(DBG_PORT)
        if not drv:
            if not (chrome_p := launch_chrome(DBG_PORT)): exit()
            launched_new = True; time.sleep(1.5)
            if not (drv := setup_driver(DBG_PORT)):
                if chrome_p and chrome_p.poll() is None: chrome_p.terminate()
                exit()
        
        if launched_new: _li(f"Переход на: {INIT_URL}"); drv.get(INIT_URL)
        else: _li("Chrome запущен, URL не открывается.")
        
        while True:
            input("ENTER для старта/повтора: ")
            q_tab_h, a_tab_h, ans_cache = None, None, None
            if not run_quiz(drv): _lw("Прогон не инициализирован.")
            _li("Прогон завершен.")
    except KeyboardInterrupt: _li("\nПрервано.")
    except NoSuchWindowException: _lc("Окно браузера закрыто.")
    except WebDriverException as e_main:
        err_str = str(e_main).lower()
        if any(s in err_str for s in ["disconnected", "target window already closed", "unable to connect"]):
            _lc(f"Связь с браузером потеряна: {e_main}")
        else: _lc(f"WebDriver ошибка: {e_main}")
    except Exception as e_main:
        _lc(f"Непредвиденная ошибка: {e_main}"); import traceback; traceback.print_exc()
    finally:
        _li("Работа завершена.")
        if chrome_p and chrome_p.poll() is None: _li("Chrome (скрипт) активен.")
