import yt_dlp
from moviepy.video.io.VideoFileClip import VideoFileClip

def download_video(url, output_path='video.mp4'):
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'outtmpl': output_path,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
    
    return info_dict.get('title', None)


def download_audio(url, output_path='audio'):
    """
    下載 YouTube 影片並轉換為 MP3
    output_path: 輸出的檔案名稱 (不需要包含 .mp3 副檔名，程式會自動加上)
    """
    
    # 如果使用者傳入的路徑包含 .mp3，先移除它以避免檔名重複 (例如 audio.mp3.mp3)
    if output_path.endswith('.mp3'):
        output_path = output_path[:-4]

    ydl_opts = {
        'format': 'bestaudio/best', # 只下載最佳音質
        'outtmpl': output_path,     # 設定輸出的檔名模板
        'postprocessors': [{        # 使用後處理器進行轉檔
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3', # 指定轉碼為 mp3
            'preferredquality': '192', # 音質設定 (192, 128, 320 等)
        }],
        'cookiefile': 'youtube_cookies.txt',  # Path to your cookies.txt
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)
    
    return info_dict.get('title', None)


def trim_video(input_path, output_path, start_time, end_time):
    with VideoFileClip(input_path) as video:
        trimmed_video = video.subclip(start_time, end_time)
        trimmed_video.write_videofile(output_path, codec='libx264')

if __name__ == '__main__':
    video_url = 'https://www.youtube.com/watch?v=AmHSKXe32Zo' 
    
    # 1. 下載影片
    # print("正在下載影片...")
    # download_video(video_url, output_path='my_video.mp4')

    # 2. 下載 MP3 (新增的功能)
    print("正在下載 MP3...")
    download_audio(video_url, output_path='my_song') 
    # 注意：檔案最後會儲存為 'my_song.mp3'

    # 3. 裁剪影片
    # trim_video('video.mp4', 'trimmed_video.mp4', start_time=0, end_time=60)
