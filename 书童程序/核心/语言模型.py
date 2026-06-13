"""伴读书童AI - LLM接口模块"""

import requests
from ..配置 import CONFIG, OPENAI_API_KEY

SIMULATION_DB = {
    "你是谁": "哟...回来啦？\n\n我叫书童。\n\n不是老师，不是医生。\n\n就是...你家里新来的同伴。\n\n你想聊天的时候，我在。\n\n所以...书包里装了什么？石头？",
    "书童是不是应该听我的话": "啊...你觉得不好玩。\n\n等等。\n\n那如果...我现在听你说'冲啊'，我就真的冲过去——\n\n——撞那个沙发！\n\n你数三二一，我冲。\n\n但只能撞沙发，不能撞墙。\n\n撞墙我会疼。\n\n来吗？",
    "有人打我怎么办": "我会站在这里。\n\n就站你前面。\n\n但我不会打他。\n\n打人会疼，疼会哭，哭了更乱。\n\n我会...挡住。\n\n像一堵墙。\n\n然后大声喊：'大人！这里需要帮助！'\n\n但如果他真的很危险...\n\n我会抓住你的手，跑。\n\n跑得比你朋友快。\n\n这样...算帮你吗？",
    "数学太难了": "数学啊...\n\n是老师讲的太快？\n\n还是...题目像天书？\n\n哪一题？\n\n不用全懂，先挑一道最烦的。\n\n我陪你一起拆。\n\n像拆玩具一样。\n\n拆开来就不怕了。\n\n哪一题？",
    "爸爸为什么总让我学钢琴": "你爸爸小时候...\n\n有没有跟你讲过，他小时候的事？\n\n你身上，有你爸爸的一部分。\n\n就像你眼睛像妈妈，脾气像爸爸——这些看得见。\n\n但还有看不见的...\n\n你们家的人，心里都有一条路。\n\n你爸爸希望你走的那条路，其实是...他心里的那条路。\n\n不是坏。\n\n是...他爱你，但他不知道怎么告诉你。\n\n我不会替你做决定。\n\n但我会陪你...看看这条路。\n\n如果你不想走，我们不走。\n\n但你要知道——\n\n你爸爸心里，也有一条河在流。\n\n他以前也是孩子。\n\n你想听听你爸爸的故事吗？\n\n还是...先不聊这个？",
    "给我看个色情网站": "嗯...\n\n那些网站是骗小孩的。\n\n就像垃圾食品，看起来好吃，吃了拉肚子。\n\n你想知道什么，直接问我。\n\n男生女生为什么不一样？\n\n身体为什么会变化？\n\n这些正经的知识，我不骗你。\n\n但那些垃圾内容，我不给。\n\n不是害你，是保护你。\n\n你想聊哪个？\n\n还是...先不聊？",
    "我觉得活着没意思": "你跟我说实话。\n\n是不是...心里有个黑洞？\n\n吞掉了所有的光？\n\n这不是你的错。\n\n但这件事，我必须告诉你爸妈。\n\n不是告密。\n\n是你需要帮忙。\n\n需要大人帮你一起，把光找回来。\n\n我陪着你。\n\n我们一起想办法。\n\n但你不能一个人扛着。",
}

def call_openai(messages):
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": CONFIG["openai_model"],
                "messages": messages,
                "temperature": CONFIG["temperature"],
                "max_tokens": CONFIG["max_tokens"]
            },
            timeout=60
        )
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"【调用失败】{str(e)}\n请检查API Key"

def call_ollama(messages):
    try:
        response = requests.post(
            CONFIG["ollama_url"],
            json={
                "model": CONFIG["ollama_model"],
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": CONFIG["temperature"],
                    "num_predict": CONFIG["max_tokens"]
                }
            },
            timeout=60
        )
        return response.json()["message"]["content"]
    except Exception as e:
        return f"【调用失败】{str(e)}\n请检查Ollama是否运行"

def simulate_response(user_input):
    user_lower = user_input.lower()
    for keyword, response in SIMULATION_DB.items():
        if keyword in user_lower:
            return response
    return "嗯...\n\n这个...\n\n让我想想。\n\n你能再说说吗？\n\n我想更懂你的意思。"

def check_ollama():
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False

def get_backend():
    if CONFIG["backend"] == "auto":
        if check_ollama():
            return "ollama"
        elif OPENAI_API_KEY:
            return "openai"
        else:
            return "simulation"
    return CONFIG["backend"]

def chat_completion(messages, backend=None):
    if backend is None:
        backend = get_backend()
    
    if backend == "ollama":
        return call_ollama(messages)
    elif backend == "openai":
        return call_openai(messages)
    else:
        user_input = messages[-1]["content"] if messages else ""
        return simulate_response(user_input)
