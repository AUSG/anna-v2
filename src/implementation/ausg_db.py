from datetime import datetime
import psycopg2

from configuration.env_configuration import Configs

class DB():
    def __init__(self):
        if Configs.LOCAL: # TODO: DB config to .env.secrets
            self.db = psycopg2.connect(host='localhost', dbname='ausg',user='postgres',password='2368a2c6a4d673af1821a21a048c77fc46af51b44e293023',port=5432)
        else:
            self.db = psycopg2.connect(host='cool-snowflake-1538.internal', dbname='ausg',user='postgres',password='2368a2c6a4d673af1821a21a048c77fc46af51b44e293023',port=5432)
        self.cursor = self.db.cursor()

    def __del__(self):
        self.db.close()
        self.cursor.close()

    def execute_r(self,query, args = tuple()):
        self.cursor.execute(query, args)
        return self.cursor.fetchall()

    def execute_cud(self,query, args = tuple()):
        self.cursor.execute(query, args)
        self.db.commit()


class AUSG_DB(DB):
    def read_tracking_threads(self):
        sql="SELECT channel, ts from public.tracking_thread WHERE enabled = true"
        return self.execute_r(sql)

    def insert_tracking_thread(self, channel, ts):
        now = str(datetime.now())
        sql="INSERT INTO public.tracking_thread (channel, ts, reg_ts, upd_ts) VALUES (%s, %s, %s, %s)"
        self.execute_cud(sql, (channel, ts, now, now))

    def delete_tracking_thread(self, channel, ts):
        sql="DELETE FROM public.tracking_thread WHERE channel = %s AND ts = %s"
        self.execute_cud(sql, (channel, ts))

    def update_tracking_thread(self, channel, ts, body):
        sql="UPDATE public.tracking_thread SET body = %s WHERE channel = %s AND ts = %s"
        self.execute_cud(sql, (body, channel, ts))
