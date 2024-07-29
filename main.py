import asyncio
import logging
import sys
import os

from environs import Env
from pytubefix import YouTube
from pytubefix.cli import on_progress
from io import BytesIO
from moviepy.editor import VideoFileClip, AudioFileClip

from aiogram import Bot, Dispatcher, html, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.methods import SendVideo
from aiogram.types import Message, FSInputFile, InputFile, InputMediaVideo, BufferedInputFile
from aiogram.utils.chat_action import ChatActionSender

from download import get_video_info
from keyboards import format_kb, admin_kb, admin_statistic_btn_text
from db import User, db

env = Env()
env.read_env()

TOKEN = env.str("BOT_TOKEN")
ADMINS = env.list("ADMINS")

dp = Dispatcher()
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(f"Hello, {html.bold(message.from_user.full_name)}!\n\nSend me a link to the YouTube video.")
    user, created = User.get_or_create(chat_id=message.chat.id, defaults={'lang': 'en', 'is_active': True})

    if str(message.chat.id) in ADMINS:
        await message.answer("You are an admin.", reply_markup=admin_kb)

    if created:
        for admin in ADMINS:
            await bot.send_message(admin, f"New user: {message.from_user.full_name} ({message.chat.id})")


@dp.message(F.text == admin_statistic_btn_text)
async def admin_statistic_handler(message: Message) -> None:
    if str(message.chat.id) not in ADMINS:
        return

    users = User.select().count()
    await message.answer(f"📊 Statistic\n\n Users: {users}", reply_markup=admin_kb)


@dp.message()
async def getlink_handler(message: Message) -> None:
    global link
    global video_info
    link = message.text
    video_info = get_video_info(link)
    await message.delete()

    if video_info is None:
        await message.answer("Error: Unable to get video information.")
        return

    formats = video_info['formats']

    caption_text = (f"📹 {video_info['title']}\n"
                    f"👤 <a href='{video_info['channel_url']}'>@{video_info['uploader']}</a>\n\n"
                    f"📥 Download formats:\n\n")

    await message.answer_photo(video_info['thumbnail'], caption=caption_text, reply_markup=format_kb(formats))


@dp.callback_query(F.data == "format_thumbnail")
async def thumbnail_callback_handler(query: types.CallbackQuery) -> None:
    await query.message.delete()
    await query.message.answer_photo(video_info['thumbnail'],
                                     caption=f"📹 {video_info['title']}\n\nThumbnail downloaded by @mega_youtube_downloader_bot")


@dp.callback_query(F.data == "format_audio")
async def audio_callback_handler(query: types.CallbackQuery) -> None:
    await query.message.delete()
    loading = await query.message.answer("⚠️ Video size is large. Please wait for a while. \n\nDownloading...")

    try:
        video = YouTube(link, on_progress_callback=on_progress)
        stream = video.streams.get_audio_only()
        stream.download(output_path="downloads", mp3=True)
        audio_buffer = open(f"downloads/{video.title}.mp3", "rb")
        audio_file = BufferedInputFile(audio_buffer.read(), filename=f"{video.title}.mp4")
        await loading.delete()
        async with ChatActionSender(bot=bot, chat_id=query.from_user.id, action="upload_audio"):
            await bot.send_audio(chat_id=query.from_user.id, audio=audio_file,
                                 caption=f"🎵 {video.title} \n\nAudio downloaded by @mega_youtube_downloader_bot")
        audio_buffer.close()
        os.remove(f"downloads/{video.title}.mp3")

    except Exception as e:
        try:
            await loading.delete()
        except Exception as e_delete:
            print(f"Error deleting loading message: {str(e_delete)}")
        await query.message.answer(f"❌ An error occurred: {str(e).replace('<', '&lt;').replace('>', '&gt;')}")


@dp.callback_query(F.data.startswith("format_"))
async def format_callback_handler(query: types.CallbackQuery) -> None:
    format_id = query.data.split("_")[1]
    await query.message.delete()
    loading = await query.message.answer("⚠️ Video size is large. Please wait for a while. \n\nDownloading...")

    try:
        video = YouTube(link, on_progress_callback=on_progress)
        stream = video.streams.get_by_itag(int(format_id))
        stream.download(output_path="downloads")
        video_buffer = open(f"downloads/{video.title}.mp4", "rb")
        video_file = BufferedInputFile(video_buffer.read(), filename=f"{video.title}.mp4")
        await loading.delete()
        async with ChatActionSender(bot=bot, chat_id=query.from_user.id, action="upload_video"):
            await bot.send_video(chat_id=query.from_user.id, video=video_file,
                                 caption=f"📹 {video.title} \n\nVideo downloaded by @mega_youtube_downloader_bot")
        video_buffer.close()
        os.remove(f"downloads/{video.title}.mp4")

    except Exception as e:
        try:
            await loading.delete()
        except Exception as e_delete:
            print(f"Error deleting loading message: {str(e_delete)}")
        await query.message.answer(f"❌ An error occurred: {str(e).replace('<', '&lt;').replace('>', '&gt;')}")


async def main() -> None:
    db.connect()
    db.create_tables([User])
    db.close()
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
