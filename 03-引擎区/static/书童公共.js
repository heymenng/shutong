/**
 * 书童公共脚本
 * 所有端口（家庭端、师父端、手机端）共用
 * 核心功能：API请求、音频播放、状态提示、全局错误处理
 */

(function() {
    'use strict';

    // ==================== 全局状态 ====================
    window.BookboyState = {
        audioUnlocked: false,
        currentAudio: null,
        token: localStorage.getItem('bookboy_token') || null
    };

    // 兼容各端口已有的 appState 状态对象
    function getAppState() {
        return window.appState || null;
    }

    function getToken() {
        const appState = getAppState();
        if (appState && appState.token) return appState.token;
        return window.BookboyState.token;
    }

    function setToken(value) {
        const appState = getAppState();
        if (appState) appState.token = value;
        window.BookboyState.token = value;
    }

    function isAudioUnlocked() {
        const appState = getAppState();
        if (appState && typeof appState.audioUnlocked !== 'undefined') {
            return appState.audioUnlocked;
        }
        return window.BookboyState.audioUnlocked;
    }

    function setAudioUnlocked(value) {
        const appState = getAppState();
        if (appState) appState.audioUnlocked = value;
        window.BookboyState.audioUnlocked = value;
    }

    // ==================== 状态栏 ====================
    function getStatusBar() {
        return document.getElementById('statusBar');
    }

    window.updateStatus = function(text) {
        const status = document.getElementById('statusText');
        if (status) status.textContent = text;
    };

    window.displayGlobalError = function(errText) {
        console.error(errText);
        const status = getStatusBar();
        if (status) {
            status.textContent = errText;
            status.style.display = 'block';
        }
    };

    // ==================== 全局错误捕获 ====================
    window.onerror = function(msg, url, line) {
        displayGlobalError(`JS错误: ${msg} (行${line})`);
        return false;
    };

    window.addEventListener('unhandledrejection', function(e) {
        displayGlobalError(`未处理Promise: ${e.reason}`);
    });

    // ==================== API请求 ====================
    window.apiFetch = async function(url, options = {}) {
        options.headers = options.headers || {};
        options.headers['Content-Type'] = 'application/json';
        const token = getToken();
        if (token) {
            options.headers['Authorization'] = `Bearer ${token}`;
        }
        const timeout = options.timeout || 60000;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);
        try {
            options.signal = controller.signal;
            const res = await fetch(url, options);
            if (res.status === 401) {
                localStorage.removeItem('bookboy_token');
                setToken(null);
                throw new Error('请先登录');
            }
            const contentType = res.headers.get('content-type') || '';
            if (contentType.includes('application/json')) {
                return await res.json();
            }
            return res;
        } finally {
            clearTimeout(timeoutId);
        }
    };

    // ==================== 音频播放 ====================

    /**
     * 获取或创建 Web Audio API 上下文
     */
    function getAudioContext() {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!AudioContext) return null;
        if (!window.__bookboyAudioContext) {
            window.__bookboyAudioContext = new AudioContext();
        }
        return window.__bookboyAudioContext;
    }

    /**
     * 在用户手势上下文中解锁音频自动播放权限
     * 同时使用 HTMLAudioElement 和 Web Audio API，兼容桌面与移动端
     */
    window.unlockAudio = async function() {
        if (isAudioUnlocked()) return true;
        let ok = false;
        // 1. 用 HTMLAudioElement 解锁
        try {
            let player = document.getElementById('chatAudioPlayer');
            if (!player) {
                player = document.createElement('audio');
                player.id = 'chatAudioPlayer';
                player.style.display = 'none';
                player.setAttribute('playsinline', 'true');
                document.body.appendChild(player);
            }
            player.muted = true;
            player.src = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=';
            await player.play();
            player.muted = false;
            ok = true;
        } catch (err) {
            console.error('HTMLAudio 解锁失败', err);
        }
        // 2. 用 Web Audio API 再解一次（iOS Safari 需要）
        try {
            const ctx = getAudioContext();
            if (ctx && ctx.state === 'suspended') {
                await ctx.resume();
            }
            if (ctx && ctx.state === 'running') {
                ok = true;
            }
        } catch (err) {
            console.error('WebAudio 解锁失败', err);
        }
        if (ok) {
            setAudioUnlocked(true);
        }
        return ok;
    };

    /**
     * 使用 Web Audio API 播放音频（移动端兜底方案）
     */
    window.playAudioWithWebAudio = async function(url, voiceLabel) {
        try {
            const ctx = getAudioContext();
            if (!ctx) {
                throw new Error('浏览器不支持 Web Audio API');
            }
            if (ctx.state === 'suspended') {
                await ctx.resume();
            }
            const res = await fetch(url, { credentials: 'same-origin' });
            if (!res.ok) throw new Error('音频下载失败: ' + res.status);
            const arrayBuffer = await res.arrayBuffer();
            const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
            const source = ctx.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(ctx.destination);
            source.start(0);
            updateStatus(voiceLabel ? (voiceLabel + ' 正在播放') : '正在播放语音');
            return true;
        } catch (err) {
            console.error('WebAudio 播放失败', err);
            return false;
        }
    };

    /**
     * 显示音频被阻止的提示按钮
     */
    window.showAudioBlockedHint = function(url, voiceLabel) {
        updateStatus('语音播放被浏览器阻止，请点击弹出的播放按钮');
        let hint = document.getElementById('audioBlockedHint');
        if (!hint) {
            hint = document.createElement('div');
            hint.id = 'audioBlockedHint';
            hint.style.cssText = 'position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:#fff3cd;color:#856404;padding:12px 20px;border-radius:8px;box-shadow:0 2px 10px rgba(0,0,0,0.2);z-index:9999;cursor:pointer;font-size:14px;';
            document.body.appendChild(hint);
        }
        hint.textContent = '🔊 点击播放语音';
        hint.onclick = () => {
            setAudioUnlocked(true);
            window.playChatAudio(url, voiceLabel);
            hint.remove();
        };
    };

    /**
     * 播放后端返回的音频
     */
    window.playChatAudio = async function(url, voiceLabel) {
        // 移动端优先尝试 Web Audio API（在用户手势中更可靠）
        if (/iPhone|iPad|iPod|Android/i.test(navigator.userAgent)) {
            const webAudioOk = await window.playAudioWithWebAudio(url, voiceLabel);
            if (webAudioOk) return;
        }

        let player = document.getElementById('chatAudioPlayer');
        if (!player) {
            player = document.createElement('audio');
            player.id = 'chatAudioPlayer';
            player.style.display = 'none';
            player.setAttribute('playsinline', 'true');
            player.setAttribute('webkit-playsinline', 'true');
            document.body.appendChild(player);
        }

        // iOS Safari 上复用同一个 audio 元素更可靠
        player.loop = false;
        player.volume = 1.0;
        player.preload = 'auto';
        player.muted = false;

        // 清理旧事件监听器
        const newPlayer = player.cloneNode(true);
        player.replaceWith(newPlayer);
        player = newPlayer;
        player.id = 'chatAudioPlayer';
        player.loop = false;
        player.volume = 1.0;
        player.preload = 'auto';
        player.style.display = 'none';
        player.setAttribute('playsinline', 'true');
        player.setAttribute('webkit-playsinline', 'true');

        let hasPlayed = false;
        const playOnce = async () => {
            if (hasPlayed) return;
            try {
                await player.play();
                hasPlayed = true;
                updateStatus(voiceLabel ? (voiceLabel + ' 正在播放') : '正在播放语音');
            } catch (err) {
                console.error('聊天语音播放失败', err);
                if (!hasPlayed) {
                    // 桌面端 fallback：尝试 Web Audio API
                    const webAudioOk = await window.playAudioWithWebAudio(url, voiceLabel);
                    if (!webAudioOk) {
                        window.showAudioBlockedHint(url, voiceLabel);
                    }
                }
            }
        };

        player.addEventListener('canplaythrough', playOnce, { once: true });
        player.addEventListener('loadedmetadata', () => {
            if (!hasPlayed && player.readyState >= 2) {
                playOnce();
            }
        }, { once: true });
        player.addEventListener('error', (e) => {
            console.error('音频加载错误', e);
            updateStatus('语音加载失败，请点击消息旁的喇叭重试');
        });

        // 先 pause 再改 src，避免旧音频继续
        player.pause();
        player.src = url + '?t=' + Date.now();
        player.load();
    };

    /**
     * 通用的音频播放函数（师父端等复用）
     */
    window.playAudio = function(url) {
        if (window.BookboyState.currentAudio) {
            window.BookboyState.currentAudio.pause();
        }
        const audio = new Audio();
        audio.preload = 'auto';
        audio.setAttribute('playsinline', 'true');
        window.BookboyState.currentAudio = audio;
        let hasPlayed = false;
        const tryPlay = async () => {
            if (hasPlayed) return;
            try {
                await audio.play();
                hasPlayed = true;
            } catch (e) {
                console.log('播放失败', e);
                if (!hasPlayed && window.showAudioBlockedHint) {
                    window.showAudioBlockedHint(url, '');
                }
            }
        };
        audio.addEventListener('canplaythrough', tryPlay, { once: true });
        audio.addEventListener('loadedmetadata', () => {
            if (!hasPlayed && audio.readyState >= 2) tryPlay();
        }, { once: true });
        audio.addEventListener('error', (e) => {
            console.error('音频加载错误', e);
            window.displayGlobalError('语音加载失败，请点重播按钮再试');
        });
        audio.src = url + '?t=' + Date.now();
        audio.load();
    };

    /**
     * 调用后端 TTS 合成语音，返回音频 URL
     * @param {string} text 要合成的文本
     * @param {string} voice 可选，指定发音人
     */
    window.synthesizeToUrl = async function(text, voice) {
        try {
            const payload = { text: text };
            if (voice) payload.voice = voice;
            const data = await apiFetch('/api/tts', {
                method: 'POST',
                body: JSON.stringify(payload)
            });
            if (data.audio_url) return data.audio_url;
            throw new Error(data.error || '语音合成失败');
        } catch (err) {
            console.error('TTS 合成失败', err);
            updateStatus('语音合成失败');
            return null;
        }
    };

    /**
     * 处理"点击播放"按钮（主要用于手机端）
     */
    window.handleAudioPlay = async function(btn, voiceLabel) {
        if (btn.dataset.loading === 'true') return;
        // 从消息气泡中获取文本（排除按钮自身文本）
        const bubble = btn.parentElement;
        let text = '';
        for (const node of bubble.childNodes) {
            if (node.nodeType === Node.TEXT_NODE) {
                text += node.textContent;
            } else if (node.nodeType === Node.ELEMENT_NODE && node !== btn && node.tagName !== 'BUTTON') {
                text += node.textContent;
            }
        }
        text = text.trim();
        if (!text) return;
        // 如果已经合成过，直接播放
        if (btn.dataset.audioUrl) {
            await unlockAudio();
            playChatAudio(btn.dataset.audioUrl, voiceLabel);
            return;
        }
        btn.dataset.loading = 'true';
        btn.innerHTML = '🔊 合成中...';
        try {
            const audioUrl = await synthesizeToUrl(text);
            if (audioUrl) {
                btn.dataset.audioUrl = audioUrl;
                btn.innerHTML = '🔊 点击播放';
                await unlockAudio();
                playChatAudio(audioUrl, voiceLabel);
            } else {
                btn.innerHTML = '🔊 合成失败';
            }
        } catch (e) {
            console.error('TTS失败', e);
            btn.innerHTML = '🔊 合成失败';
        } finally {
            btn.dataset.loading = 'false';
        }
    };

    /**
     * 播放测试音频，用于检查语音是否正常
     */
    window.testAudio = async function() {
        await unlockAudio();
        playChatAudio('/static/测试音频.mp3', '测试');
    };

    /**
     * 获取用户头像 URL，未上传时返回 null
     */
    window.getUserAvatarUrl = function(userId) {
        if (!userId) return null;
        return `/avatar/${userId}.jpg?t=${Date.now()}`;
    };

    /**
     * 后台合成语音并更新最后一条 assistant 消息的"点击播放"按钮
     * 用于手机端：先显示文字，后台合成，合成完更新按钮
     */
    window.synthesizeAndUpdateLastButton = async function(text, voiceLabel) {
        const audioUrl = await synthesizeToUrl(text);
        const messages = document.querySelectorAll('.message.assistant');
        if (!messages.length) return;
        const last = messages[messages.length - 1];
        const btn = last.querySelector('.audio-play-hint');
        if (!btn) return;
        if (audioUrl) {
            btn.dataset.audioUrl = audioUrl;
            if (btn.dataset.loading !== 'true') {
                btn.innerHTML = '🔊 点击播放';
            }
            // 通知各端口的状态对象
            const appState = getAppState();
            if (appState) {
                appState.lastAudioUrl = audioUrl;
                appState.lastVoiceLabel = voiceLabel;
            }
        } else {
            if (btn.dataset.loading !== 'true') {
                btn.innerHTML = '🔊 合成失败';
            }
        }
    };

    // ==================== 通用工具 ====================

    window.escapeHtml = function(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    };

    // 页面加载成功标记（不再自动显示顶部黄条，避免占用空间；出错时再用）
    (function() {
        const status = getStatusBar();
        if (status) {
            status.textContent = '页面脚本已加载';
        }
    })();

})();
