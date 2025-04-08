import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pygame
import os
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
from PIL import Image, ImageTk, ImageDraw, ImageFont
from tkinterdnd2 import DND_FILES, TkinterDnD
import pyaudio
import time
import traceback
import configparser
from PyQt5.QtWidgets import QApplication
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtCore import QByteArray, Qt
from PyQt5.QtGui import QPixmap, QPainter, QImage
import json
import sys

class MusicPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("シンプル音楽プレイヤー")
        
        # 実行ファイルのパスを取得
        if getattr(sys, 'frozen', False):
            # PyInstallerでビルドされた場合
            self.base_path = os.path.dirname(sys.executable)
        else:
            # 通常のPythonスクリプトとして実行された場合
            self.base_path = os.path.dirname(os.path.abspath(__file__))
        
        # 設定ファイルのパスを設定
        self.config_file = os.path.join(self.base_path, "settings.ini")
        
        # 設定ファイルの読み込み
        self.config = configparser.ConfigParser()
        self.load_settings()
        
        # ウィンドウサイズを設定
        try:
            width = int(self.config['Window']['width'])
            height = int(self.config['Window']['height'])
            self.root.geometry(f"{width}x{height}")
        except Exception as e:
            print(f"ウィンドウサイズの設定中にエラーが発生しました: {e}")
            self.root.geometry("800x600")
        
        # 音楽プレイヤーの初期化
        pygame.mixer.init()
        
        # プレイリスト
        self.playlist = []
        self.current_track = 0
        self.current_track_length = 0  # 現在の曲の長さ（秒）
        self.current_position = 0  # 現在の再生位置（秒）
        self.last_update_time = 0  # 最後に更新した時間
        self.repeat_track = False  # トラックリピートフラグ
        self.is_paused = True  # 一時停止状態を記録
        
        # オーディオデバイスの初期化
        self.p = pyaudio.PyAudio()
        self.audio_devices = self.get_audio_devices()
        self.current_device_index = self.p.get_default_output_device_info()['index']
        
        # ドラッグ&ドロップの設定
        self.root.drop_target_register(DND_FILES)
        self.root.dnd_bind('<<Drop>>', self.drop_files)
        
        # Qt5の初期化
        self.qt_app = QApplication.instance()
        if not self.qt_app:
            self.qt_app = QApplication([])
        
        self.create_widgets()
        self.set_audio_device()  # 保存された設定を適用
        self.update_audio_device_info()
        
        # プログレスバーの更新用タイマー
        self.update_progress()
        
        # プレイリストの復元（最後に実行）
        self.restore_playlist()
        
    def get_audio_devices(self):
        devices = []
        for i in range(self.p.get_device_count()):
            device_info = self.p.get_device_info_by_index(i)
            if device_info['maxOutputChannels'] > 0:  # 出力デバイスのみを取得
                devices.append((i, device_info['name']))
        return devices
        
    def create_widgets(self):
        # ステータスバー
        self.status_frame = tk.Frame(self.root, bd=1, relief=tk.SUNKEN)
        self.status_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)
        
        # デバイス選択用のフレーム
        device_frame = tk.Frame(self.status_frame)
        device_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # デバイス選択用のラベル
        device_label = tk.Label(device_frame, text="オーディオデバイス: ")
        device_label.pack(side=tk.LEFT)
        
        # デバイス選択用のコンボボックス
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(device_frame, textvariable=self.device_var, state="readonly", width=50)
        self.device_combo['values'] = [name for _, name in self.audio_devices]
        self.device_combo.pack(side=tk.LEFT, padx=5)
        self.device_combo.bind('<<ComboboxSelected>>', self.on_device_change)
        
        # 保存されたデバイス名を取得して設定
        try:
            saved_device_name = self.config['Audio']['device_name']
            if saved_device_name:  # デバイス名が指定されている場合
                for i, (_, device_name) in enumerate(self.audio_devices):
                    if device_name == saved_device_name:
                        self.device_combo.current(i)
                        self.current_device_index = i
                        print(f"保存されたデバイスを設定しました: {saved_device_name}")
                        break
        except Exception as e:
            print(f"保存されたデバイスの設定中にエラーが発生しました: {e}")
            self.device_combo.current(self.current_device_index)
        
        # デバイス情報を表示するラベル
        self.device_info_label = tk.Label(self.status_frame, text="", anchor=tk.W)
        self.device_info_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Treeviewのスタイルを設定
        style = ttk.Style()
        style.theme_use('default')  # デフォルトテーマを使用
        style.configure("Treeview.Heading", 
                       background="#808080",  # より薄めのグレーに変更
                       foreground="white", 
                       font=('', 10, 'bold'),
                       relief="flat")  # 境界線を削除
        style.map("Treeview.Heading",
                 background=[('active', '#808080')])  # ホバー時の背景色も同じ色に
        style.configure("Treeview", 
                       background="white", 
                       foreground="black", 
                       fieldbackground="white")
        style.configure("Treeview.Column", 
                       background="#404040", 
                       width=20)  # 再生中マーク用の列のスタイル
        
        # 保存されたカラム幅を設定
        try:
            track_width = int(self.config['Columns']['track_width'])
            title_width = int(self.config['Columns']['title_width'])
            artist_width = int(self.config['Columns']['artist_width'])
            duration_width = int(self.config['Columns']['duration_width'])
        except Exception as e:
            print(f"カラム幅の設定中にエラーが発生しました: {e}")
            track_width = 30
            title_width = 400
            artist_width = 200
            duration_width = 70
        
        # プレイリスト表示用のTreeview
        self.tree = ttk.Treeview(self.root, columns=("playing", "track", "title", "artist", "duration"), show="headings", style="Treeview")
        self.tree.heading("playing", text="")  # 再生中マーク用の列
        self.tree.heading("track", text="TRK")  # 「トラック」を「TRK」に変更
        self.tree.heading("title", text="曲名")
        self.tree.heading("artist", text="アーティスト")
        self.tree.heading("duration", text="Time")  # 「再生時間」を「Time」に変更
        self.tree.column("playing", width=20, anchor="center", stretch=False)  # 再生中マーク用の列
        self.tree.column("track", width=track_width, anchor="e", stretch=False)  # 固定幅
        self.tree.column("title", width=title_width, stretch=True)  # 伸縮可能
        self.tree.column("artist", width=artist_width, stretch=True)  # 伸縮可能
        self.tree.column("duration", width=duration_width, anchor="e", stretch=False)  # 固定幅で右端に配置
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # ダブルクリックイベントの設定
        self.tree.bind("<Double-1>", self.play_selected)
        
        # キーボードイベントの設定
        self.root.bind("<Return>", self.on_enter_key)
        self.root.bind("<Delete>", self.on_delete_key)
        self.root.bind("<space>", self.on_space_key)  # スペースキーのバインドを追加
        self.root.bind("<Left>", self.on_left_key)  # 左カーソルキーのバインドを追加
        self.root.bind("<Right>", self.on_right_key)  # 右カーソルキーのバインドを追加
        self.root.bind("<Control-Left>", self.on_ctrl_left_key)  # Ctrl+左矢印のバインドを追加
        self.root.bind("<Control-Right>", self.on_ctrl_right_key)  # Ctrl+右矢印のバインドを追加
        self.tree.bind("<Up>", self.on_up_key)
        self.tree.bind("<Down>", self.on_down_key)
        
        # プログレスバーと時間表示用のフレーム
        progress_frame = tk.Frame(self.root, bd=2, relief=tk.GROOVE, padx=5, pady=5)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 現在再生中の曲名を表示するラベル
        self.current_track_label = tk.Label(progress_frame, text="再生中の曲: ", anchor=tk.W)
        self.current_track_label.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))
        
        # 現在の再生位置を表示するラベル
        self.current_time_label = tk.Label(progress_frame, text="00:00")
        self.current_time_label.pack(side=tk.LEFT)
        
        # プログレスバー
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # プログレスバーのクリックイベントを設定
        self.progress_bar.bind('<Button-1>', self.on_progress_click)
        
        # 曲の長さを表示するラベル
        self.total_time_label = tk.Label(progress_frame, text="00:00")
        self.total_time_label.pack(side=tk.LEFT)
        
        # コントロールボタン
        control_frame = tk.Frame(self.root)
        control_frame.pack(pady=10)
        
        # ボタンのスタイルを設定
        style = ttk.Style()
        style.configure('Icon.TButton', 
                      padding=5, 
                      relief='flat',
                      background='#404040',  # 濃いグレー
                      foreground='white',  # テキスト色を白に
                      font=('', 12))  # フォントサイズを12に変更
        style.map('Icon.TButton',
                 background=[('active', '#505050')])  # ホバー時の色も少し明るく
        
        # アイコンの読み込み
        try:
            # SVGファイルを読み込んでアイコンとして使用
            self.prev_icon = self.load_svg_to_photoimage("icons/prev.svg")
            self.rewind_10_icon = self.load_svg_to_photoimage("icons/rewind_10.svg")
            self.rewind_5_icon = self.load_svg_to_photoimage("icons/rewind_5.svg")
            self.play_icon = self.load_svg_to_photoimage("icons/play.svg")
            self.pause_icon = self.load_svg_to_photoimage("icons/pause.svg")
            self.forward_5_icon = self.load_svg_to_photoimage("icons/forward_5.svg")
            self.forward_10_icon = self.load_svg_to_photoimage("icons/forward_10.svg")
            self.next_icon = self.load_svg_to_photoimage("icons/next.svg")
            self.repeat_off_icon = self.load_svg_to_photoimage("icons/repeat_off.svg")
            self.repeat_on_icon = self.load_svg_to_photoimage("icons/repeat_on.svg")
        except Exception as e:
            # アイコンが読み込めない場合はテキストボタンを使用
            self.prev_icon = None
            self.rewind_10_icon = None
            self.rewind_5_icon = None
            self.play_icon = None
            self.pause_icon = None
            self.forward_5_icon = None
            self.forward_10_icon = None
            self.next_icon = None
            self.repeat_off_icon = None
            self.repeat_on_icon = None
        
        # ボタンの作成
        self.prev_button = ttk.Button(control_frame, style='Icon.TButton', 
                                    image=self.prev_icon if self.prev_icon else None,
                                    text="前の曲" if not self.prev_icon else "",
                                    command=self.prev_track)
        self.prev_button.pack(side=tk.LEFT, padx=5)
        self.prev_button.bind("<Enter>", lambda e: self.show_tooltip(e, "前の曲"))
        self.prev_button.bind("<Leave>", lambda e: self.hide_tooltip())
        
        self.rewind_10_button = ttk.Button(control_frame, style='Icon.TButton',
                                         image=self.rewind_10_icon if self.rewind_10_icon else None,
                                         text="10秒戻し" if not self.rewind_10_icon else "",
                                         command=lambda: self.rewind(10))
        self.rewind_10_button.pack(side=tk.LEFT, padx=5)
        self.rewind_10_button.bind("<Enter>", lambda e: self.show_tooltip(e, "10秒戻し"))
        self.rewind_10_button.bind("<Leave>", lambda e: self.hide_tooltip())
        
        self.rewind_5_button = ttk.Button(control_frame, style='Icon.TButton',
                                        image=self.rewind_5_icon if self.rewind_5_icon else None,
                                        text="5秒戻し" if not self.rewind_5_icon else "",
                                        command=lambda: self.rewind(5))
        self.rewind_5_button.pack(side=tk.LEFT, padx=5)
        self.rewind_5_button.bind("<Enter>", lambda e: self.show_tooltip(e, "5秒戻し"))
        self.rewind_5_button.bind("<Leave>", lambda e: self.hide_tooltip())
        
        # 再生ボタン
        self.play_button = ttk.Button(control_frame, style='Icon.TButton',
                                    image=self.play_icon if self.play_icon else None,
                                    text="再生" if not self.play_icon else "",
                                    command=self.toggle_play,
                                    width=30)  # ボタンの幅を1.5倍に
        self.play_button.pack(side=tk.LEFT, padx=5)
        self.play_button.bind("<Enter>", lambda e: self.show_tooltip(e, "再生/一時停止"))
        self.play_button.bind("<Leave>", lambda e: self.hide_tooltip())
        
        self.forward_5_button = ttk.Button(control_frame, style='Icon.TButton',
                                         image=self.forward_5_icon if self.forward_5_icon else None,
                                         text="5秒進め" if not self.forward_5_icon else "",
                                         command=lambda: self.forward(5))
        self.forward_5_button.pack(side=tk.LEFT, padx=5)
        self.forward_5_button.bind("<Enter>", lambda e: self.show_tooltip(e, "5秒進め"))
        self.forward_5_button.bind("<Leave>", lambda e: self.hide_tooltip())
        
        self.forward_10_button = ttk.Button(control_frame, style='Icon.TButton',
                                          image=self.forward_10_icon if self.forward_10_icon else None,
                                          text="10秒進め" if not self.forward_10_icon else "",
                                          command=lambda: self.forward(10))
        self.forward_10_button.pack(side=tk.LEFT, padx=5)
        self.forward_10_button.bind("<Enter>", lambda e: self.show_tooltip(e, "10秒進め"))
        self.forward_10_button.bind("<Leave>", lambda e: self.hide_tooltip())
        
        self.next_button = ttk.Button(control_frame, style='Icon.TButton',
                                    image=self.next_icon if self.next_icon else None,
                                    text="次の曲" if not self.next_icon else "",
                                    command=self.next_track)
        self.next_button.pack(side=tk.LEFT, padx=5)
        self.next_button.bind("<Enter>", lambda e: self.show_tooltip(e, "次の曲"))
        self.next_button.bind("<Leave>", lambda e: self.hide_tooltip())
        
        # リピートボタン
        self.repeat_button = ttk.Button(control_frame, style='Icon.TButton',
                                      image=self.repeat_off_icon if self.repeat_off_icon else None,
                                      text="リピート: OFF" if not self.repeat_off_icon else "",
                                      command=self.toggle_repeat)
        self.repeat_button.pack(side=tk.LEFT, padx=5)
        self.repeat_button.bind("<Enter>", lambda e: self.show_tooltip(e, "リピート: OFF"))
        self.repeat_button.bind("<Leave>", lambda e: self.hide_tooltip())
        
        # ツールチップ用のラベルを作成
        self.tooltip = tk.Label(self.root, text="", background="#ffffe0", relief="solid", borderwidth=1, font=('', 12))
        self.tooltip.place_forget()  # 最初は非表示
    
    def toggle_repeat(self):
        if not self.playlist:  # プレイリストが空の場合は何もしない
            return
        
        self.repeat_track = not self.repeat_track
        if self.repeat_on_icon and self.repeat_off_icon:
            self.repeat_button.configure(
                image=self.repeat_on_icon if self.repeat_track else self.repeat_off_icon
            )
        else:
            self.repeat_button.configure(
                text=f"リピート: {'ON' if self.repeat_track else 'OFF'}"
            )
    
    def forward(self, seconds):
        if not self.playlist:  # プレイリストが空の場合は何もしない
            return
        
        if pygame.mixer.music.get_busy():
            self.current_position = min(self.current_track_length, self.current_position + seconds)
            pygame.mixer.music.set_pos(self.current_position)
            self.last_update_time = time.time()
    
    def rewind(self, seconds):
        if not self.playlist:  # プレイリストが空の場合は何もしない
            return
        
        if pygame.mixer.music.get_busy():
            self.current_position = max(0, self.current_position - seconds)
            pygame.mixer.music.set_pos(self.current_position)
            self.last_update_time = time.time()
    
    def on_progress_click(self, event):
        if self.current_track_length > 0:
            # クリック位置から再生位置を計算
            progress_bar_width = self.progress_bar.winfo_width()
            click_x = event.x
            percentage = click_x / progress_bar_width
            new_position = self.current_track_length * percentage
            
            # 再生位置を変更
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.set_pos(new_position)
            else:
                pygame.mixer.music.load(self.playlist[self.current_track])
                pygame.mixer.music.play(start=new_position)
                self.play_button.config(text="一時停止")
            
            # 現在の再生位置を更新
            self.current_position = new_position
            self.last_update_time = time.time()
            
            # プログレスバーと時間表示を即座に更新
            self.progress_var.set(percentage * 100)
            self.current_time_label.config(text=self.format_time(new_position))
    
    def format_time(self, seconds):
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    def update_progress(self):
        if not self.is_paused:  # 一時停止中は更新しない
            current_time = time.time()
            elapsed = current_time - self.last_update_time
            self.current_position += elapsed
            self.last_update_time = current_time
            
            # プログレスバーの更新
            if self.current_track_length > 0:
                # 曲の長さを超えないように制限
                if self.current_position > self.current_track_length:
                    self.current_position = self.current_track_length
                
                progress = (self.current_position / self.current_track_length) * 100
                self.progress_var.set(progress)
                
                # 経過時間の表示を更新
                self.current_time_label.config(text=self.format_time(self.current_position))
            
            # 曲が終了した場合
            if self.current_position >= self.current_track_length and self.playlist:  # 再生中の場合のみ次の曲へ
                print(f"曲の再生が終了しました (再生状態: {'一時停止中' if self.is_paused else '再生中' if pygame.mixer.music.get_busy() else '停止中'})")
                if self.repeat_track:
                    print("リピートモード: 同じ曲を先頭から再生します")
                    self.current_position = 0
                    pygame.mixer.music.load(self.playlist[self.current_track])
                    pygame.mixer.music.play()
                else:
                    print("次の曲に進みます")
                    self.next_track()  # 次の曲を再生
        
        self.root.after(100, self.update_progress)
        
    def on_device_change(self, event):
        selected_index = self.device_combo.current()
        if selected_index >= 0:
            # 現在の再生状態を保存
            was_playing = pygame.mixer.music.get_busy()
            current_pos = self.current_position if was_playing else 0
            
            # 新しいデバイスを設定
            self.current_device_index = self.audio_devices[selected_index][0]
            
            # pygameを再初期化
            pygame.mixer.quit()
            pygame.mixer.init(devicename=self.audio_devices[selected_index][1])
            
            # デバイス情報を更新
            self.update_audio_device_info()
            
            # 再生中だった場合は、新しいデバイスで再生を再開
            if was_playing and self.playlist:
                pygame.mixer.music.load(self.playlist[self.current_track])
                pygame.mixer.music.play(start=current_pos)
                self.play_button.config(text="一時停止")
                self.current_position = current_pos
                self.last_update_time = time.time()
    
    def update_audio_device_info(self):
        try:
            device_info = self.p.get_device_info_by_index(self.current_device_index)
            device_name = device_info.get('name', '不明')
            device_type = "USB" if "USB" in device_name.upper() else "内蔵"
            channels = device_info.get('maxOutputChannels', 2)
            sample_rate = device_info.get('defaultSampleRate', 44100)
            
            # pygameの情報も取得
            pygame_info = pygame.mixer.get_init()
            if pygame_info:
                pygame_freq, pygame_format, pygame_channels = pygame_info
                device_text = (
                    f"チャンネル: {channels}, サンプルレート: {sample_rate}Hz\n"
                    f"Pygame設定: {pygame_freq}Hz, フォーマット: {pygame_format}, チャンネル: {pygame_channels}"
                )
            else:
                device_text = f"チャンネル: {channels}, サンプルレート: {sample_rate}Hz"
            
        except Exception as e:
            device_text = f"オーディオデバイス情報の取得に失敗しました: {str(e)}"
        
        self.device_info_label.config(text=device_text)
        
    def drop_files(self, event):
        print(f"ドラッグアンドドロップ開始 (再生状態: {'一時停止中' if self.is_paused else '再生中' if pygame.mixer.music.get_busy() else '停止中'})")
        # Windowsのパス形式に対応
        files = event.data.split('} {')
        for file in files:
            # 中括弧を削除
            file = file.strip('{}')
            if file.lower().endswith('.mp3'):
                print(f"MP3ファイルを検出: {file}")
                # ダブルクリックイベントを一時的に無効化
                print("ダブルクリックイベントを無効化")
                self.tree.unbind("<Double-1>")
                print("プレイリストに追加開始")
                self.add_to_playlist(file)  # 自動再生は行わない
                print("プレイリストに追加完了")
                # 選択状態を解除
                print("選択状態を解除")
                self.tree.selection_clear()
                # 100ms後にダブルクリックイベントを再バインド
                print("ダブルクリックイベントを再バインド予約")
                self.root.after(100, lambda: self.tree.bind("<Double-1>", self.play_selected))
        print(f"ドラッグアンドドロップ終了 (再生状態: {'一時停止中' if self.is_paused else '再生中' if pygame.mixer.music.get_busy() else '停止中'})")

    def add_to_playlist(self, file_path):
        print(f"プレイリストに追加開始: {file_path} (再生状態: {'一時停止中' if self.is_paused else '再生中' if pygame.mixer.music.get_busy() else '停止中'})")
        try:
            # MP3ファイルのメタデータを取得
            audio = MP3(file_path)
            title = audio.get('TIT2', [os.path.basename(file_path)])[0]
            artist = audio.get('TPE1', ['Unknown Artist'])[0]
            track_number = audio.get('TRCK', ['0'])[0]
            duration = self.format_time(audio.info.length)
        except:
            title = os.path.basename(file_path)
            artist = "Unknown Artist"
            track_number = "0"
            duration = "00:00"
        
        print(f"メタデータ取得完了: {title} - {artist}")
        self.playlist.append(file_path)
        print("プレイリストにファイルパスを追加")
        self.tree.insert("", "end", values=("", track_number, title, artist, duration))  # 再生中マーク用の列を追加
        print("Treeviewにアイテムを追加")
        # 再生中マークの更新は行わない（再生していないため）
        print(f"プレイリストに追加完了: {title} - {artist} (再生状態: {'一時停止中' if self.is_paused else '再生中' if pygame.mixer.music.get_busy() else '停止中'})")
        
        # 現在の再生状態を保持
        was_playing = pygame.mixer.music.get_busy()
        if was_playing:
            pygame.mixer.music.pause()
            self.play_button.config(text="再生")
            self.is_paused = True
    
    def play_selected(self, event):
        print(f"ダブルクリックによる再生開始 (再生状態: {'一時停止中' if self.is_paused else '再生中' if pygame.mixer.music.get_busy() else '停止中'})")
        selection = self.tree.selection()
        if selection:
            self.current_track = self.tree.index(selection[0])
            print(f"選択された曲のインデックス: {self.current_track}")
            self.play_track()
    
    def play_track(self):
        """選択された曲を再生"""
        if not self.playlist:  # プレイリストが空の場合は何もしない
            return
        
        try:
            # 再生を開始
            pygame.mixer.music.load(self.playlist[self.current_track])
            pygame.mixer.music.play()
            self.is_paused = False
            # アイコンを一時停止用に変更
            if self.pause_icon:
                self.play_button.configure(image=self.pause_icon)
            else:
                self.play_button.configure(text="一時停止")
            
            # 曲の長さを取得
            audio = MP3(self.playlist[self.current_track])
            self.current_track_length = audio.info.length
            
            # 曲名を表示
            try:
                tags = ID3(self.playlist[self.current_track])
                title = str(tags.get('TIT2', [''])[0])
                artist = str(tags.get('TPE1', [''])[0])
                if not title:
                    title = os.path.basename(self.playlist[self.current_track])
                if not artist:
                    artist = "Unknown Artist"
            except:
                title = os.path.basename(self.playlist[self.current_track])
                artist = "Unknown Artist"
            
            self.current_track_label.config(text=f"再生中の曲: {title} - {artist}")
            
            # 再生中マークを更新
            self.update_playing_mark()
            
        except Exception as e:
            print(f"曲の再生中にエラーが発生しました: {e}")
            # エラーが発生した場合は、アイコンを再生用に変更
            self.is_paused = True
            if self.play_icon:
                self.play_button.configure(image=self.play_icon)
            else:
                self.play_button.configure(text="再生")
    
    def toggle_play(self):
        """再生/一時停止を切り替える"""
        if not self.playlist:  # プレイリストが空の場合は何もしない
            return
        
        if self.is_paused:
            pygame.mixer.music.unpause()
            self.is_paused = False
            # アイコンを一時停止用に変更
            if self.pause_icon:
                self.play_button.configure(image=self.pause_icon)
            else:
                self.play_button.configure(text="一時停止")
        else:
            pygame.mixer.music.pause()
            self.is_paused = True
            # アイコンを再生用に変更
            if self.play_icon:
                self.play_button.configure(image=self.play_icon)
            else:
                self.play_button.configure(text="再生")
    
    def next_track(self):
        if not self.playlist:  # プレイリストが空の場合は何もしない
            return
        
        if self.current_track < len(self.playlist) - 1:
            self.current_track += 1
            self.current_position = 0
            self.last_update_time = time.time()
            self.progress_var.set(0)
            self.play_track()
    
    def prev_track(self):
        if not self.playlist:  # プレイリストが空の場合は何もしない
            return
        
        if self.current_track > 0:
            self.current_track -= 1
            self.current_position = 0
            self.last_update_time = time.time()
            self.progress_var.set(0)
            self.play_track()
    
    def on_enter_key(self, event):
        """Enterキーで選択された曲を先頭から再生する"""
        if not self.playlist:  # プレイリストが空の場合は何もしない
            return
        
        selection = self.tree.selection()
        if not selection:  # 選択されていない場合は何もしない
            return
        
        try:
            # 選択された曲を再生
            selected_index = self.tree.index(selection[0])
            self.current_track = selected_index
            self.current_position = 0  # 再生位置をリセット
            self.last_update_time = time.time()  # 更新時間をリセット
            self.progress_var.set(0)  # プログレスバーをリセット
            self.current_time_label.config(text="00:00")  # 時間表示をリセット
            self.play_track()
            
        except Exception as e:
            print(f"Enterキーの処理中にエラーが発生しました: {e}")
    
    def on_delete_key(self, event):
        """Deleteキーで選択された曲を削除"""
        if not self.playlist:  # プレイリストが空の場合は何もしない
            return
        
        selection = self.tree.selection()
        if not selection:  # 選択されていない場合は何もしない
            return
        
        try:
            # 選択されたアイテムのインデックスを取得
            selected_item = selection[0]
            selected_index = self.tree.index(selected_item)
            
            # 選択された曲が現在再生中の曲の場合
            if selected_index == self.current_track:
                # 再生を停止
                pygame.mixer.music.stop()
                self.play_button.config(text="再生")
                self.is_paused = True
            
            # 曲をプレイリストから削除
            del self.playlist[selected_index]
            self.tree.delete(selected_item)  # 選択されたアイテムを削除
            
            # 現在の再生位置を更新
            if self.current_track >= len(self.playlist):
                self.current_track = max(0, len(self.playlist) - 1)
            
            # プレイリストが空になった場合
            if not self.playlist:
                self.current_track = 0
                self.current_track_length = 0
                self.current_position = 0
                self.progress_var.set(0)
                self.current_time_label.config(text="00:00")
                self.total_time_label.config(text="00:00")
                self.current_track_label.config(text="再生中の曲: ")
            else:
                # 削除された曲の次の曲を選択（最後の曲の場合は新たな最後の曲を選択）
                next_index = min(selected_index, len(self.playlist) - 1)
                if next_index >= 0:  # インデックスが有効な場合のみ
                    next_item = self.tree.get_children()[next_index]
                    self.tree.selection_set(next_item)
                    self.tree.focus(next_item)
                    self.tree.see(next_item)
            
            self.update_playing_mark()  # 再生中マークを更新
            
        except Exception as e:
            print(f"曲の削除中にエラーが発生しました: {e}")
            # エラーが発生した場合は、プレイリストを再構築
            self.update_playlist_display()
    
    def on_up_key(self, event):
        # 上矢印キーの処理
        selection = self.tree.selection()
        if selection:
            current_index = self.tree.index(selection[0])
            if current_index > 0:
                prev_item = self.tree.get_children()[current_index - 1]
                self.tree.selection_set(prev_item)
                self.tree.focus(prev_item)
                self.tree.see(prev_item)
        return "break"  # イベントの伝播を停止

    def on_down_key(self, event):
        # 下矢印キーの処理
        selection = self.tree.selection()
        if selection:
            current_index = self.tree.index(selection[0])
            if current_index < len(self.playlist) - 1:
                next_item = self.tree.get_children()[current_index + 1]
                self.tree.selection_set(next_item)
                self.tree.focus(next_item)
                self.tree.see(next_item)
        return "break"  # イベントの伝播を停止
    
    def update_playing_mark(self):
        # すべての行の再生中マークをクリア
        for item in self.tree.get_children():
            self.tree.set(item, "playing", "")
        
        # 現在再生中の曲にマークを表示
        if self.playlist and pygame.mixer.music.get_busy():
            current_item = self.tree.get_children()[self.current_track]
            self.tree.set(current_item, "playing", ">")
    
    def on_space_key(self, event):
        self.toggle_play()
        return "break"  # イベントの伝播を停止
    
    def on_left_key(self, event):
        self.rewind(5)  # 5秒戻し
        return "break"  # イベントの伝播を停止

    def on_right_key(self, event):
        self.forward(5)  # 5秒進め
        return "break"  # イベントの伝播を停止

    def on_ctrl_left_key(self, event):
        self.rewind(10)  # 10秒戻し
        return "break"  # イベントの伝播を停止

    def on_ctrl_right_key(self, event):
        self.forward(10)  # 10秒進め
        return "break"  # イベントの伝播を停止
    
    def __del__(self):
        # PyAudioの終了処理
        if hasattr(self, 'p'):
            self.p.terminate()

    def load_settings(self):
        """設定ファイルを読み込む"""
        if os.path.exists(self.config_file):
            self.config.read(self.config_file, encoding='utf-8')
        else:
            # デフォルト設定
            self.config['Audio'] = {'device_name': ''}  # 空文字列はデフォルトデバイスを意味する
            self.config['Window'] = {'width': '800', 'height': '600'}
            self.config['Columns'] = {
                'track_width': '30',
                'title_width': '400',
                'artist_width': '200',
                'duration_width': '70'
            }
            self.config['Playlist'] = {}  # プレイリスト用のセクションを追加

    def restore_playlist(self):
        """プレイリストを復元する"""
        if 'Playlist' in self.config:
            for key in self.config['Playlist']:
                file_path = self.config['Playlist'][key]
                if os.path.exists(file_path):  # ファイルが存在する場合のみ追加
                    self.add_to_playlist(file_path)

    def save_settings(self):
        """設定をファイルに保存する"""
        # プレイリストの保存
        self.config['Playlist'] = {}  # プレイリストセクションをクリア
        for i, file_path in enumerate(self.playlist):
            self.config['Playlist'][f'item_{i}'] = file_path
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            self.config.write(f)

    def set_audio_device(self):
        """保存された再生デバイスを設定する"""
        try:
            saved_device_name = self.config['Audio']['device_name']
            if saved_device_name:  # デバイス名が指定されている場合
                devices = self.get_audio_devices()
                # デバイス名に一致するデバイスを探す
                for device_id, device_name in devices:
                    if device_name == saved_device_name:
                        pygame.mixer.quit()
                        pygame.mixer.init(devicename=device_name)
                        self.current_device_index = device_id
                        self.device_var.set(device_name)
                        print(f"再生デバイスを設定しました: {device_name}")
                        return
                print("保存されたデバイスが見つかりません。デフォルトデバイスを使用します。")
            else:
                print("デフォルトデバイスを使用します。")
            pygame.mixer.quit()
            pygame.mixer.init()
        except Exception as e:
            print(f"デバイス設定中にエラーが発生しました: {e}")
            print("デフォルトデバイスを使用します。")
            pygame.mixer.quit()
            pygame.mixer.init()

    def on_closing(self):
        """ウィンドウを閉じる時の処理"""
        # 現在の再生デバイス名を保存
        try:
            current_device_name = self.device_var.get()
            self.config['Audio']['device_name'] = current_device_name
            
            # ウィンドウサイズを保存
            self.config['Window']['width'] = str(self.root.winfo_width())
            self.config['Window']['height'] = str(self.root.winfo_height())
            
            # カラム幅を保存
            self.config['Columns']['track_width'] = str(self.tree.column("track", "width"))
            self.config['Columns']['title_width'] = str(self.tree.column("title", "width"))
            self.config['Columns']['artist_width'] = str(self.tree.column("artist", "width"))
            self.config['Columns']['duration_width'] = str(self.tree.column("duration", "width"))
            
            self.save_settings()
        except Exception as e:
            print(f"設定の保存中にエラーが発生しました: {e}")
        
        pygame.mixer.quit()
        self.root.destroy()

    def create_text_icon(self, text):
        """テキストを使用したアイコンを作成する"""
        width = 24
        height = 24
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype("arial.ttf", 20)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
        return ImageTk.PhotoImage(image)

    def load_svg_to_photoimage(self, svg_path, width=32, height=32):
        """SVGファイルをPhotoImageに変換する"""
        try:
            # 実行環境に応じてアイコンファイルのパスを設定
            if getattr(sys, 'frozen', False):
                # PyInstallerでビルドされた場合
                icon_path = os.path.join(sys._MEIPASS, svg_path)
            else:
                # 通常のPythonスクリプトとして実行された場合
                icon_path = os.path.join(self.base_path, svg_path)
            
            # SVGファイルを読み込む
            with open(icon_path, 'rb') as f:
                svg_data = f.read()
            
            # SVGレンダラーを作成
            renderer = QSvgRenderer(QByteArray(svg_data))
            
            # QImageを作成してSVGを描画
            image = QImage(width, height, QImage.Format_ARGB32)
            image.fill(Qt.transparent)
            painter = QPainter(image)
            renderer.render(painter)
            painter.end()
            
            # QImageをPIL Imageに変換
            image_data = image.constBits().asstring(image.byteCount())
            pil_image = Image.frombuffer('RGBA', (width, height), image_data, 'raw', 'BGRA')
            
            # PIL ImageをPhotoImageに変換
            photo_image = ImageTk.PhotoImage(pil_image)
            return photo_image
        except Exception as e:
            print(f"アイコンの読み込みに失敗しました: {e}")
            return None

    def show_tooltip(self, event, text):
        """ツールチップを表示する"""
        # ツールチップの位置を計算
        x = event.widget.winfo_rootx() + event.widget.winfo_width() + 5
        y = event.widget.winfo_rooty() + (event.widget.winfo_height() - self.tooltip.winfo_height()) // 2
        
        # ツールチップのテキストと位置を設定
        self.tooltip.config(text=text)
        self.tooltip.update_idletasks()  # サイズを更新
        self.tooltip.place(x=x, y=y)
        self.tooltip.lift()  # 最前面に表示

    def hide_tooltip(self):
        """ツールチップを非表示にする"""
        self.tooltip.place_forget()

    def clear_playlist(self):
        """プレイリストをクリアする"""
        # 再生を停止
        pygame.mixer.music.stop()
        self.play_button.config(text="再生")
        self.is_paused = True
        
        # プレイリストをクリア
        self.playlist.clear()
        self.current_track = 0
        self.current_track_length = 0
        self.current_position = 0
        self.progress_var.set(0)
        self.current_time_label.config(text="00:00")
        self.total_time_label.config(text="00:00")
        self.current_track_label.config(text="再生中の曲: ")
        
        # Treeviewをクリア
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 設定ファイルのプレイリストセクションもクリア
        if 'Playlist' in self.config:
            self.config['Playlist'] = {}
            self.save_settings()

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = MusicPlayer(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)  # ウィンドウを閉じる時の処理を設定
    root.mainloop() 