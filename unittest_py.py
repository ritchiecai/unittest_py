#coding: utf-8

import re
import unittest
import requests
import urllib
import json
import ConfigParser
from urlparse import urljoin
import sys
reload(sys)
sys.setdefaultencoding('utf-8')

from pb import cms_pb2 
from protobuf_to_dict import protobuf_to_dict, dict_to_protobuf


from google.protobuf.service_reflection import GeneratedServiceType as ServiceType
from google.protobuf.reflection import GeneratedProtocolMessageType as MessageType
from google.protobuf.descriptor_pb2 import FieldDescriptorProto


# 基本思路：
# 1. 通过分析pb生成的代码，获取接口列表以及每个接口的请求参数和应答值。
#   需要对参数做基本的类型分析，用于后续创建基本的测试用例
# 2. 定义metaclass，用于生成unittest子类。该类可以：
#   根据参数类型做基本的测试用例生成
#   读取外部文件配置的测试数据，数据格式需要和参数匹配，读取的参数包含：请求和应答
# 3. 


def PrintMethod(method_desc):
    print "rpc name: " + method_desc.name
    print "service HTTP method: " + method_desc.GetOptions().Extensions[getattr(cms_pb2, 'method_option')]
    print "service HTTP url: " + method_desc.GetOptions().Extensions[getattr(cms_pb2, 'url_option')]



# load test case data from config file
config = ConfigParser.SafeConfigParser()
config.read('unittest_data.ini')

region = config.get('General', 'region')

def GetUnittestData(service_method, entry):
    try:
        content = config.get(service_method, entry)
    except:
        content = None
    return content

def HasUnittestData(service_method):
    return config.has_section(service_method)

def GetBaseUrl():
    return config.get('General', 'base_url')


log = open('log', 'w')


def setUp(self):
    # login
    self.http_session = requests.Session()

    base_url = GetBaseUrl()
    login_url = urljoin(base_url, 'admin/login')
    #self.http_session.post('http://10.6.208.208:8000/cgi-bin/music_cms/admin/login', data={'name':'guest', 'passwd':'guest123'})
    self.http_session.post(login_url, data={'name':'guest', 'passwd':'guest123'})

    pass

def tearDown(self):
    pass


def CheckDictContain(src, dst):
    """
        判断字典src中的（key，value）是否都包含在dst中。
        如果包含，返回True；否则返回False
    """
    src_set = set(src.items())
    dst_set = set(dst.items())

    if src_set <= dst_set:
        return True
    else:
        return False
    
def CheckDictContain_v2(src, dst):
    """
        判断字典src中的（key，value）是否都包含在dst中。
        如果包含，返回True；否则返回False


        所谓包含：
        1. 对于dict，键值对需要包含，dst中多出的键值对不影响结果
        2. 对于list，按照顺序一一对应，dst多出的元素不影响结果
        3. 对于其他类型（set除外），值相等
        
    """
    for k, v in src.items():
        if not dst.has_key(k):
            return False
        
        if type(v) != type(dst[k]):
            return False

        if isinstance(v, list):
            l1 = len(v)
            l2 = len(dst[k])
            if l1 > l2:
                return False
            i = 0
            while i < l1:
                if type(v[i]) != type(dst[k][i]):
                    return False

                if isinstance(v[i], dict):
                    res = CheckDictContain_v2(v[i], dst[k][i])
                    if not res:
                        return False
                
                else:
                    if v[i] != dst[k][i]:
                        return False
                i += 1
            return True

        elif isinstance(v, dict):
            res = CheckDictContain_v2(v, dst[k])
            if not res:
                return False

        else:
            if v != dst[k]:
                return False

            return True
    



def BaseTestFunc_v2(req, files, resp):
    def TestFunc(self, req=req, files=files, resp=resp):


        if self.http_method == "POST":
            
            log.write("URL[%s]\n\tPOST data: %s\n\tresp: %s\n\n" % (self.url,  json.dumps(req), json.dumps(resp)))
            
            
            # send the request
            if files:
                r = self.http_session.post(self.url, data=req, files=files)
            else:
                r = self.http_session.post(self.url, data=req)

            self.assertEqual(r.status_code, 200)

            real_resp = r.json()

            #print real_resp
            # check the resp
            
            self.assertTrue(CheckDictContain_v2(resp, real_resp))                

            res = True
            try:
                dict_to_protobuf(self.resp_type, real_resp)
            except Exception, e:
                res = False
            
            self.assertTrue(res)
            

                
        elif self.http_method == "GET":
            
            get_param = urllib.urlencode(req)
            
            log.write("URL[%s]\n\tGET data: %s\n\tresp: %s\n\n" % (self.url, get_param, json.dumps(resp)))

            # send the request
            r = self.http_session.get(self.url, params=req)

            self.assertEqual(r.status_code, 200)

            real_resp = r.json()
            #print real_resp

            self.assertTrue(CheckDictContain_v2(resp, real_resp))
            #self.assertDictContainsSubset(resp, real_resp)
            res = True
            try:
                dict_to_protobuf(self.resp_type, real_resp)
            except Exception, e:
                res = False
            
            self.assertTrue(res)
            
        else:
            pass
    
    return TestFunc

class TestCaseMetaClass(type):
    """

    """
    def __new__(cls, name, dct):
        return super(TestCaseMetaClass, cls).__new__(cls, name, (unittest.TestCase,), dct)
    
    def __init__(cls, name, dct):
        super(TestCaseMetaClass, cls).__init__(cls, name, dct)
    

def TransferReq(http_method, config_section_name, req_type, req_name):

    #print "section: %s, entry: %s" % (config_section_name, req_name)
    req = json.loads(GetUnittestData(config_section_name, req_name))
    files = {}
    if http_method == "GET":
        req.update({'region_id': region})
    
    elif http_method == "POST":
        req.update({'region_id': region})
        # check if there is a file need to be POSTED
        for field_desc in req_type.DESCRIPTOR.fields:
            if field_desc.type == FieldDescriptorProto.TYPE_BYTES and field_desc.has_options:
                # 具有options的bytes类型字段
                if field_desc.GetOptions().Extensions[cms_pb2.is_file]:
                    # 是一个文件，POST时需要做特殊处理
                    # 保存文件名
                    files[field_desc.name] = open(req[field_desc.name], 'rb')
                    req.pop(field_desc.name)
                    
    return (req, files)


    
def DoUnittest(service):

    base_url = GetBaseUrl()

    for method_desc in service.DESCRIPTOR.methods:

        req_type = service.GetRequestClass(method_desc)
        resp_type = service.GetResponseClass(method_desc)

        config_section_name = '_'.join((service.DESCRIPTOR.name, method_desc.name))

        # check if there is test data
        if not HasUnittestData(config_section_name):
            print "no test data for %s, just skip" % (method_desc.name)
            continue
        
        http_method = method_desc.GetOptions().Extensions[getattr(cms_pb2, 'method_option')]

        # 生成类使用
        dct = {}
        dct['req_type'] = req_type
        dct['resp_type'] = resp_type
        dct['setUp'] = setUp
        dct['tearDown'] = tearDown
        dct['http_method'] = http_method
        dct['url'] = urljoin(base_url, method_desc.GetOptions().Extensions[getattr(cms_pb2, 'url_option')])

        unittest_data_count = int(GetUnittestData(config_section_name, 'count'))
        
        count = 0
        while count <  unittest_data_count:
            req_name = 'req' + str(count)
            req_file_name = 'files' + str(count)
            resp_name = 'resp' + str(count)

            req, files = TransferReq(http_method, config_section_name, req_type, req_name)
            resp = json.loads(GetUnittestData(config_section_name, resp_name))
            
            test_func_name = "test" + method_desc.name + str(count)
            dct[test_func_name] = BaseTestFunc_v2(req, files, resp)

            count += 1


        MyTestCase = TestCaseMetaClass('MyTestCase', dct)
        suite = unittest.TestLoader().loadTestsFromTestCase(MyTestCase)
        unittest.TextTestRunner(verbosity=2).run(suite)



# get all the service & method
def main():
    d = dir(cms_pb2)

    for it in d:
        elem = getattr(cms_pb2, it)
        if isinstance(elem, ServiceType):
            # check if it is a test stub
            m = re.search(r'.*(_Stub)', it)
            if m:
                # this is a test stub
                pass
                #print "find a test stub: " + str(it)
                
            else:
                # this is a service
                print "----------"
                print "\033[1;31;40m" + "find service: " + str(it) + "\033[0m"
                print "start unitttest..."
                DoUnittest(elem)
                print "----------"
            
        elif isinstance(it, MessageType):
            pass
            print "find message: " + str(elem)
        else:
            pass
            #print "other type attr: " + it



if __name__ == "__main__":
    main()
