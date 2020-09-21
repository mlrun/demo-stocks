from kfp import dsl
from mlrun import mount_v3io, mlconf
import os
from nuclio.triggers import V3IOStreamTrigger

funcs = {}
projdir = os.path.join('/', 'User', 'demo-stocks')
# model_filepath = os.path.join(projdir, 'models', 'bert_sentiment_analysis_model.pt')
model_filepath = os.path.join(projdir, 'models', 'model.pt')
reviews_datafile = os.path.join(projdir, 'data', 'reviews.csv')


def init_functions(functions: dict, project=None, secrets=None):
    for f in functions.values():
        # Add V3IO Mount
        f.apply(mount_v3io())
        
        # Always pull images to keep updates
        f.spec.image_pull_policy = 'Always'
    
    # Define inference-stream related triggers
    functions['sentiment_analysis_server'].add_model('bert_classifier_v1', model_filepath)
    functions['sentiment_analysis_server'].spec.readiness_timeout = 500
    functions['sentiment_analysis_server'].set_config('readinessTimeoutSeconds', 500)
                
        
@dsl.pipeline(
    name='Stocks demo deployer',
    description='Up to RT Stocks ingestion and analysis'
)
def kfpipeline(
    # General
    V3IO_CONTAINER = 'bigdata',
    STOCKS_TSDB_TABLE = 'stocks/stocks_tsdb',
    STOCKS_KV_TABLE = 'stocks/stocks_kv',
    STOCKS_STREAM = 'stocks/stocks_stream',
    RUN_TRAINER = False,
    
    # Trainer
    pretrained_model = 'bert-base-cased',
    reviews_dataset = reviews_datafile,
    models_dir = 'models',
    model_filename = 'bert_sentiment_analysis_model.pt',
    n_classes = 3,
    MAX_LEN = 128,
    BATCH_SIZE = 16,
    EPOCHS =  1,
    random_state = 42,
    
    # stocks reader
    STOCK_LIST = ['GOOG', 'MSFT', 'AMZN', 'AAPL', 'INTC'],
    EXPRESSION_TEMPLATE = "symbol='{symbol}';price={price};volume={volume};last_updated='{last_updated}'",
    
    # Sentiment analysis server
    model_name = 'bert_classifier_v1',
    model_filepath = model_filepath # if not trained
    
    ):
    
    with dsl.Condition(RUN_TRAINER == True):
        
        trainer_image_builder = funcs['bert_sentiment_classifier_trainer'].deploy_step(skip_deployed=True)
        
        trainer = funcs['bert_sentiment_classifier_trainer'].as_step(name='bert_sentiment_classifier_trainer',
                                                                     params={'pretrained_model': pretrained_model,
                                                                             'EPOCHS': EPOCHS,
                                                                             'models_dir': models_dir,
                                                                             'model_filename': model_filename,
                                                                             'n_classes': n_classes,
                                                                             'MAX_LEN': MAX_LEN,
                                                                             'BATCH_SIZE': BATCH_SIZE,
                                                                             'EPOCHS': EPOCHS,
                                                                             'random_state': random_state},
                                                                     inputs={'reviews_dataset': reviews_dataset},
                                                                     image=trainer_image_builder.outputs['image'],
                                                                     outputs=['bert_sentiment_analysis_model'])
        
        sentiment_server = funcs['sentiment_analysis_server'].deploy_step(env={f'SERVING_MODEL_{model_name}': trainer.outputs['bert_sentiment_analysis_model']})
        
        news_reader = funcs['news_reader'].deploy_step(env={'V3IO_CONTAINER': V3IO_CONTAINER,
                                                        'STOCKS_STREAM': STOCKS_STREAM,
                                                        'SENTIMENT_MODEL_ENDPOINT': sentiment_server.outputs['endpoint']})
    
    with dsl.Condition(RUN_TRAINER == False):
        
        sentiment_server = funcs['sentiment_analysis_server'].deploy_step(env={f'SERVING_MODEL_{model_name}': model_filepath})
        
        news_reader = funcs['news_reader'].deploy_step(env={'V3IO_CONTAINER': V3IO_CONTAINER,
                                                        'STOCKS_STREAM': STOCKS_STREAM,
                                                        'SENTIMENT_MODEL_ENDPOINT': sentiment_server.outputs['endpoint']})
    
    stocks_reader = funcs['stocks_reader'].deploy_step(env={'STOCK_LIST': STOCK_LIST,
                                                            'V3IO_CONTAINER': V3IO_CONTAINER,
                                                            'STOCKS_TSDB_TABLE': STOCKS_TSDB_TABLE,
                                                            'STOCKS_KV_TABLE': STOCKS_KV_TABLE,
                                                            'EXPRESSION_TEMPLATE': EXPRESSION_TEMPLATE})
    
    stream_viewer = funcs['stream_viewer'].deploy_step(env={'V3IO_CONTAINER': V3IO_CONTAINER,
                                                            'STOCKS_STREAM': STOCKS_STREAM})
    
    grafana_dashboard = funcs['grafana'].as_step(name='grafana_deployer',
                                                 params={streamview_url: stream_viewer.outputs['endpoint'],
                                                         v3io_container: V3IO_CONTAINER,
                                                         stocks_kv_table: STOCKS_KV_TABLE,
                                                         stocks_tsdb_table: STOCKS_TSDB_TABLE})
    
