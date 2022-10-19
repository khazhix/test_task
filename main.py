import asyncio
import os
import struct
import uuid
from abc import ABC
from hashlib import md5

import ffmpeg
import tornado.web
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

TRIM_VIDEO_PATH = 'trim_results'
UPLOADS_PATH = 'uploads'

if not os.path.exists(TRIM_VIDEO_PATH):
    os.makedirs(TRIM_VIDEO_PATH)

if not os.path.exists(UPLOADS_PATH):
    os.makedirs(UPLOADS_PATH)

Base = declarative_base()


class Vidaq(Base):
    __tablename__ = 'vidaq'

    id = Column(Integer, primary_key=True, nullable=False, autoincrement=True)
    chunks = Column(Integer, nullable=False)
    hash = Column(UUID, nullable=False)
    original_name = Column(String, nullable=False)


def is_float_try(str):
    try:
        float(str)
        return True
    except ValueError:
        return False


def is_int_try(str):
    try:
        int(str)
        return True
    except ValueError:
        return False


def calc_video_uuid(video_body: bytes, pitch: float) -> str:
    pitch_bytes = bytearray(struct.pack("f", pitch))
    video_and_pitch = video_body + pitch_bytes
    md5_v_p = md5(video_and_pitch).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, md5_v_p))


class DownloadHandler(tornado.web.RequestHandler, ABC):
    def get(self):
        video_id = self.get_argument('id')
        if not video_id:
            self.set_status(400)
            self.write_error(400)
            return

        if not is_int_try(video_id):
            self.set_status(400)
            self.write_error(400)
            return

        video_id = int(video_id)

        engine = create_engine("postgresql://vidaq_admin:vidaq1234@localhost/vidaq", echo=True)
        with Session(engine) as session:
            vidaq_entry = session.query(Vidaq).get(video_id)

        if not vidaq_entry:
            self.set_status(400, reason='Entry doesn\'t exist')
            self.write_error(400)
            return

        original_name_wo_ext = os.path.splitext(vidaq_entry.original_name)[0]
        host_name = f'{self.request.protocol}://{self.request.host}'
        playlist_filename = f'{TRIM_VIDEO_PATH}/{vidaq_entry.id}/{original_name_wo_ext}.m3u8'
        with open(playlist_filename) as f:
            filedata = f.read()

        if not f'{self.request.protocol}://{self.request.host}' in filedata:
            filedata = filedata.replace(original_name_wo_ext,
                                        f'{host_name}/{TRIM_VIDEO_PATH}/{vidaq_entry.id}/{original_name_wo_ext}')
            with open(playlist_filename, 'w') as f:
                f.write(filedata)

        self.write(f'{host_name}/{playlist_filename}')


class UploadHandler(tornado.web.RequestHandler, ABC):

    def post(self):
        engine = create_engine("postgresql://vidaq_admin:vidaq1234@localhost/vidaq", echo=True)

        files_input = self.request.files.get('video')
        if not files_input:
            self.set_status(400)
            self.write_error(400)
            return

        video_input = files_input[0]
        if not ("video" in video_input.content_type):
            self.set_status(415)
            self.write_error(415)
            return

        pitch_input = self.request.body_arguments.get('pitch', ['1.0'])
        if pitch_input:
            pitch_input = pitch_input[0]

        if is_float_try(pitch_input):
            pitch_input = float(pitch_input)
            pitch_input = 1.0 if pitch_input < 0 else pitch_input
        else:
            pitch_input = 1.0

        video_uuid = calc_video_uuid(video_input.body, pitch_input)
        with Session(engine) as session:
            video_id = session.query(Vidaq.id).filter(Vidaq.hash == video_uuid).scalar()

        if video_id:
            self.set_status(200)
            self.write(str(video_id))
            return

        video_path = "uploads/" + video_input.filename
        output_file = open(video_path, 'wb')
        output_file.write(video_input['body'])

        video_stream = ffmpeg.input(video_path)
        video_info = ffmpeg.probe(video_path)

        video_len = float(video_info.get("format").get("duration"))
        a_sample_rate = int(video_info.get("streams")[1].get('sample_rate'))

        with Session(engine) as session:
            vidaq_entry = Vidaq(
                chunks=video_len,
                hash=video_uuid,
                original_name=video_input.filename
            )
            session.add(vidaq_entry)
            session.commit()
            session.refresh(vidaq_entry)
            video_id = vidaq_entry.id

        trim_video_path = f'{TRIM_VIDEO_PATH}/{video_id}'
        full_outuput_path = os.path.splitext(f'{trim_video_path}/{video_input.filename}')[0]
        os.mkdir(trim_video_path)

        audio = video_stream.audio
        video = video_stream.video
        if pitch_input != 1:
            audio = video_stream.audio.filter('asetrate', a_sample_rate * pitch_input) \
                .filter('aresample', a_sample_rate) \
                .filter('atempo', 1 / pitch_input)

        ffmpeg.output(audio, video,
                      f'{full_outuput_path}.m3u8',
                      format='hls',
                      force_key_frames='expr:gte(t,n_forced*1)',
                      hls_flags='independent_segments',
                      hls_time=1,
                      hls_list_size=0).run()

        self.write(str(video_id))


def make_app():
    return tornado.web.Application([
        (r"/download", DownloadHandler),
        (r"/upload", UploadHandler),
        (f"/{TRIM_VIDEO_PATH}/(.*)", tornado.web.StaticFileHandler, {'path': TRIM_VIDEO_PATH})
    ])


async def main():
    app = make_app()
    app.listen(8888)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
