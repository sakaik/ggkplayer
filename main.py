import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pygame
import os
from mutagen.mp3 import MP3
from tkinterdnd2 import DND_FILES, TkinterDnD
import pyaudio
import time
import traceback
import configparser

class MusicPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("シンプル音楽プレイヤー")
        
        # 設定ファイルの読み込み
        self.config = configparser.ConfigParser()
        self.config_file = "settings.ini"
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
        
        self.create_widgets()
        self.set_audio_device()  # 保存された設定を適用
        self.update_audio_device_info()
        
        # プログレスバーの更新用タイマー
        self.update_progress()
        
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
        
        # ボタンの作成
        self.prev_button = tk.Button(control_frame, text="前の曲", command=self.prev_track, width=10, height=2)
        self.prev_button.pack(side=tk.LEFT, padx=5)
        
        self.rewind_10_button = tk.Button(control_frame, text="10秒戻し", command=lambda: self.rewind(10), width=10, height=2)
        self.rewind_10_button.pack(side=tk.LEFT, padx=5)
        
        self.rewind_5_button = tk.Button(control_frame, text="5秒戻し", command=lambda: self.rewind(5), width=10, height=2)
        self.rewind_5_button.pack(side=tk.LEFT, padx=5)
        
        self.play_button = tk.Button(control_frame, text="再生", command=self.toggle_play, width=10, height=2)
        self.play_button.pack(side=tk.LEFT, padx=5)
        
        self.forward_5_button = tk.Button(control_frame, text="5秒進め", command=lambda: self.forward(5), width=10, height=2)
        self.forward_5_button.pack(side=tk.LEFT, padx=5)
        
        self.forward_10_button = tk.Button(control_frame, text="10秒進め", command=lambda: self.forward(10), width=10, height=2)
        self.forward_10_button.pack(side=tk.LEFT, padx=5)
        
        self.next_button = tk.Button(control_frame, text="次の曲", command=self.next_track, width=10, height=2)
        self.next_button.pack(side=tk.LEFT, padx=5)
        
        # リピートボタン
        self.repeat_button = tk.Button(control_frame, text="リピート: OFF", command=self.toggle_repeat, width=10, height=2)
        self.repeat_button.pack(side=tk.LEFT, padx=5)
    
    def toggle_repeat(self):
        self.repeat_track = not self.repeat_track
        self.repeat_button.config(text=f"リピート: {'ON' if self.repeat_track else 'OFF'}")
    
    def forward(self, seconds):
        if pygame.mixer.music.get_busy():
            self.current_position = min(self.current_track_length, self.current_position + seconds)
            pygame.mixer.music.set_pos(self.current_position)
            self.last_update_time = time.time()
    
    def rewind(self, seconds):
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
            #print(f"Debug:{self.current_position}/{self.current_track_length} {self.current_position >= self.current_track_length }: {pygame.mixer.music.get_busy()}")
            # if self.current_position >= self.current_track_length and self.playlist and pygame.mixer.music.get_busy():  # 再生中の場合のみ次の曲へ
            if self.current_position >= self.current_track_length and self.playlist :  # 再生中の場合のみ次の曲へ
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
        print(f"再生開始: インデックス {self.current_track} (再生状態: {'一時停止中' if self.is_paused else '再生中' if pygame.mixer.music.get_busy() else '停止中'})")
        if self.playlist:
            self.is_paused = False
            pygame.mixer.music.load(self.playlist[self.current_track])
            pygame.mixer.music.play()
            self.play_button.config(text="一時停止")
            
            # 曲の長さを取得
            try:
                audio = MP3(self.playlist[self.current_track])
                self.current_track_length = audio.info.length
                self.total_time_label.config(text=self.format_time(self.current_track_length))
                
                # 曲名を更新
                title = audio.get('TIT2', [os.path.basename(self.playlist[self.current_track])])[0]
                self.current_track_label.config(text=f"再生中の曲: {title}")
                print(f"再生曲情報: {title} (長さ: {self.current_track_length}秒)")
            except:
                self.current_track_length = 0
                self.total_time_label.config(text="00:00")
                self.current_track_label.config(text=f"再生中の曲: {os.path.basename(self.playlist[self.current_track])}")
                print(f"再生曲情報: {os.path.basename(self.playlist[self.current_track])} (メタデータ取得失敗)")
            
            # 再生位置をリセット
            self.current_position = 0
            self.last_update_time = time.time()
            
            # 現在のトラックを選択状態にする
            self.tree.selection_set(self.tree.get_children()[self.current_track])
            self.update_playing_mark()  # 再生中マークを更新
    
    def toggle_play(self):
        print(f"再生/一時停止切り替え (再生状態: {'一時停止中' if self.is_paused else '再生中' if pygame.mixer.music.get_busy() else '停止中'})")
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.pause()
            self.play_button.config(text="再生")
            self.is_paused = True
        else:
            if self.is_paused:
                pygame.mixer.music.unpause()
                self.last_update_time = time.time()
            else:
                if self.playlist:
                    self.play_track()
            self.play_button.config(text="一時停止")
            self.is_paused = False
    
    def next_track(self):
        print(f"次の曲へ (再生状態: {'一時停止中' if self.is_paused else '再生中' if pygame.mixer.music.get_busy() else '停止中'})")
        if self.playlist:
            self.current_track = (self.current_track + 1) % len(self.playlist)
            self.current_position = 0
            self.last_update_time = time.time()
            self.progress_var.set(0)
            self.play_track()
    
    def prev_track(self):
        print(f"前の曲へ (再生状態: {'一時停止中' if self.is_paused else '再生中' if pygame.mixer.music.get_busy() else '停止中'})")
        if self.playlist:
            self.current_track = (self.current_track - 1) % len(self.playlist)
            self.current_position = 0
            self.last_update_time = time.time()
            self.progress_var.set(0)
            self.play_track()
    
    def on_enter_key(self, event):
        # Enterキーの処理
        selection = self.tree.selection()
        if selection:
            selected_index = self.tree.index(selection[0])
            
            # 選択された曲が現在再生中の曲と同じ場合
            if selected_index == self.current_track and pygame.mixer.music.get_busy():
                # 再生を停止
                pygame.mixer.music.stop()
                self.play_button.config(text="再生")
            else:
                # 選択された曲を再生
                self.current_track = selected_index
                self.play_track()
    
    def on_delete_key(self, event):
        # Deleteキーの処理
        selection = self.tree.selection()
        if selection:
            selected_index = self.tree.index(selection[0])
            
            # 選択された曲が現在再生中の曲の場合
            if selected_index == self.current_track:
                # 再生を停止
                pygame.mixer.music.stop()
                self.play_button.config(text="再生")
                self.current_track = 0  # 最初の曲を選択
            
            # 曲をプレイリストから削除
            self.tree.delete(selected_index)  # 選択されたアイテムのIDを使用
            del self.playlist[selected_index]
            
            # 現在の再生位置を更新
            if self.current_track >= len(self.playlist):
                self.current_track = max(0, len(self.playlist) - 1)
            
            # プレイリストが空になった場合
            if not self.playlist:
                self.current_track = 0
                self.current_track_length = 0
                self.current_position = 0  # 再生位置をリセット
                self.progress_var.set(0)
                self.current_time_label.config(text="00:00")
                self.total_time_label.config(text="00:00")
                self.current_track_label.config(text="再生中の曲: ")
            else:
                # 削除された曲の次の曲を選択（最後の曲の場合は新たな最後の曲を選択）
                next_index = min(selected_index, len(self.playlist) - 1)
                next_item = self.tree.get_children()[next_index]
                self.tree.selection_set(next_item)
                self.tree.focus(next_item)  # フォーカスを設定
                self.tree.see(next_item)  # 選択されたアイテムが見えるようにスクロール
            self.update_playing_mark()  # 再生中マークを更新
    
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
            self.save_settings()

    def save_settings(self):
        """設定をファイルに保存する"""
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

if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = MusicPlayer(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)  # ウィンドウを閉じる時の処理を設定
    root.mainloop() 