import os
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    WTF_CSRF_ENABLED = True
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'hard to guess string'
    SSL_DISABLE = False
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True
    SQLALCHEMY_RECORD_QUERIES = True
    MAIL_SERVER = 'smtpmail.hbk.com'
    MAIL_PORT = 25
    MAIL_USE_TLS = True
    # MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    # MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    CELERY_BROKER_URL = 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'

    DB = {
        "ENTERPRISE": "Driver={SQL Server Native Client 10.0};Server=DALDATA1,1433;Database=Enterprise;Trusted_Connection=Yes;",
        "REFERENCE": "Driver={SQL Server Native Client 10.0};Server=DALDATA5,1633;Database=Reference;Trusted_Connection=Yes;",
        "VENDORREF": "Driver={SQL Server Native Client 10.0};Server=DALDATA5,1633;Database=Vendor;Trusted_Connection=Yes;",
        "VENDOR": "Driver={SQL Server Native Client 10.0};Server=DALDATA1,1433;Database=Vendor;Trusted_Connection=Yes;",
        "VENDORQS": "Driver={SQL Server Native Client 10.0};Server=DALDATA9,1433;Database=Vendor;Trusted_Connection=Yes;",
        "STATARB": "Driver={SQL Server Native Client 10.0};Server=DALDATA1,1433;Database=StatArb;Trusted_Connection=Yes;",
        "LOANPERFORMANCE": "Driver={SQL Server Native Client 10.0};Server=DALSCDATA1;Database=LoanPerformance;Trusted_Connection=Yes;",
        "EMBS": "Driver={SQL Server Native Client 10.0};Server=DALSCDATA1;Database=EMBS;Trusted_Connection=Yes;",
        "EMBSHIST": "Driver={SQL Server Native Client 10.0};Server=DALSCDATA1;Database=EMBSHIST;Trusted_Connection=Yes;",
        "VENDORSC": "Driver={SQL Server Native Client 10.0};Server=DALSCDATA1;Database=Vendor;Trusted_Connection=Yes;"
    }



    @staticmethod
    def init_app(app):
        pass


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'data-dev.sqlite')


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'data-test.sqlite')
    WTF_CSRF_ENABLED = False


# class ProductionConfig(Config):
#     SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
#         'sqlite:///' + os.path.join(basedir, 'data.sqlite')
#     DB = {
#         "ENTERPRISE": "Driver={SQL Server Native Client 10.0};Server=DALDATA1,1433;Database=Enterprise;Trusted_Connection=Yes;",
#         "REFERENCE": "Driver={SQL Server Native Client 10.0};Server=DALDATA5,1633;Database=Reference;Trusted_Connection=Yes;",
#         "VENDORREF": "Driver={SQL Server Native Client 10.0};Server=DALDATA5,1633;Database=Vendor;Trusted_Connection=Yes;",
#         "VENDOR": "Driver={SQL Server Native Client 10.0};Server=DALDATA1,1433;Database=Vendor;Trusted_Connection=Yes;",
#         "VENDORQS": "Driver={SQL Server Native Client 10.0};Server=DALDATA9,1433;Database=Vendor;Trusted_Connection=Yes;",
#         "STATARB": "Driver={SQL Server Native Client 10.0};Server=DALDATA1,1433;Database=StatArb;Trusted_Connection=Yes;",
#         "LOANPERFORMANCE": "Driver={SQL Server Native Client 10.0};Server=DALSCDATA1;Database=LoanPerformance;Trusted_Connection=Yes;",
#         "EMBS": "Driver={SQL Server Native Client 10.0};Server=DALSCDATA1;Database=EMBS;Trusted_Connection=Yes;",
#         "EMBSHIST": "Driver={SQL Server Native Client 10.0};Server=DALSCDATA1;Database=EMBSHIST;Trusted_Connection=Yes;",
#         "VENDORSC": "Driver={SQL Server Native Client 10.0};Server=DALSCDATA1;Database=Vendor;Trusted_Connection=Yes;"
#     }
# #     @classmethod
#     def init_app(cls, app):
#         Config.init_app(app)

#         # email errors to the administrators
#         import logging
#         from logging.handlers import SMTPHandler
#         credentials = None
#         secure = None
#         if getattr(cls, 'MAIL_USERNAME', None) is not None:
#             credentials = (cls.MAIL_USERNAME, cls.MAIL_PASSWORD)
#             if getattr(cls, 'MAIL_USE_TLS', None):
#                 secure = ()
#         mail_handler = SMTPHandler(
#             mailhost=(cls.MAIL_SERVER, cls.MAIL_PORT),
#             fromaddr=cls.FLASKY_MAIL_SENDER,
#             toaddrs=[cls.FLASKY_ADMIN],
#             subject=cls.FLASKY_MAIL_SUBJECT_PREFIX + ' Application Error',
#             credentials=credentials,
#             secure=secure)
#         mail_handler.setLevel(logging.ERROR)
#         app.logger.addHandler(mail_handler)




config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    # 'production': ProductionConfig,

    'default': DevelopmentConfig
}
