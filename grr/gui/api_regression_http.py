#!/usr/bin/env python
"""Base test classes for API handlers tests."""



import json
import os

import portpicker
import requests

from google.protobuf import json_format
import logging

from grr import gui
from grr.gui import api_auth_manager
from grr.gui import api_call_router
from grr.gui import api_value_renderers
from grr.gui import http_api
from grr.gui import wsgiapp_testlib
from grr.gui.api_client.connectors import http_connector
from grr.lib import flags
from grr.lib import testing_startup
from grr.lib import utils

DOCUMENT_ROOT = os.path.join(os.path.dirname(gui.__file__), "static")


class HttpApiRegressionTestMixinBase(object):
  """Load only API E2E test cases."""

  api_version = None
  endpoint = None

  @classmethod
  def setUpClass(cls):  # pylint: disable=invalid-name
    if cls.api_version not in [1, 2]:
      raise ValueError("api_version may be 1 or 2 only")

    if not HttpApiRegressionTestMixinBase.endpoint:
      port = portpicker.PickUnusedPort()
      logging.info("Picked free AdminUI port %d.", port)

      testing_startup.TestInit()
      # Force creation of new APIAuthorizationManager.
      api_auth_manager.APIACLInit.InitApiAuthManager()

      trd = wsgiapp_testlib.ServerThread(port)
      trd.StartAndWaitUntilServing()

      cls.endpoint = "http://localhost:%d" % port

  def setUp(self):  # pylint: disable=invalid-name
    super(HttpApiRegressionTestMixinBase, self).setUp()
    self.connector = http_connector.HttpConnector(
        api_endpoint=self.__class__.endpoint)

  def _ParseJSON(self, json_str):
    """Parses response JSON."""

    xssi_prefix = ")]}'\n"
    if json_str.startswith(xssi_prefix):
      json_str = json_str[len(xssi_prefix):]

    return json.loads(json_str)

  def _PrepareV1Request(self, method, args=None):
    """Prepares API v1 request for a given method and args."""

    args_proto = None
    if args:
      args_proto = args.AsPrimitiveProto()
    request = self.connector.BuildRequest(method, args_proto)
    request.url = request.url.replace("/api/v2/", "/api/")
    if args and request.data:
      body_proto = args.__class__().AsPrimitiveProto()
      json_format.Parse(request.data, body_proto)
      body_args = args.__class__()
      body_args.ParseFromString(body_proto.SerializeToString())
      request.data = json.dumps(
          api_value_renderers.StripTypeInfo(
              api_value_renderers.RenderValue(body_args)),
          cls=http_api.JSONEncoderWithRDFPrimitivesSupport)

    prepped_request = request.prepare()

    return request, prepped_request

  def _PrepareV2Request(self, method, args=None):
    """Prepares API v2 request for a given method and args."""

    args_proto = None
    if args:
      args_proto = args.AsPrimitiveProto()
    request = self.connector.BuildRequest(method, args_proto)
    prepped_request = request.prepare()

    return request, prepped_request

  def HandleCheck(self, method_metadata, args=None, replace=None):
    """Does regression check for given method, args and a replace function."""

    if not replace:
      raise ValueError("replace can't be None")

    if self.__class__.api_version == 1:
      request, prepped_request = self._PrepareV1Request(
          method_metadata.name, args=args)
    elif self.__class__.api_version == 2:
      request, prepped_request = self._PrepareV2Request(
          method_metadata.name, args=args)
    else:
      raise ValueError("api_version may be only 1 or 2, not %d",
                       flags.FLAGS.api_version)

    session = requests.Session()
    response = session.send(prepped_request)

    check_result = {
        "url": replace(prepped_request.path_url),
        "method": request.method
    }

    if request.data:
      request_payload = self._ParseJSON(replace(request.data))
      if request_payload:
        check_result["request_payload"] = request_payload

    if (method_metadata.result_type ==
        api_call_router.RouterMethodMetadata.BINARY_STREAM_RESULT_TYPE):
      check_result["response"] = replace(utils.SmartUnicode(response.content))
    else:
      check_result["response"] = self._ParseJSON(replace(response.content))

    if self.__class__.api_version == 1:
      stripped_response = api_value_renderers.StripTypeInfo(
          check_result["response"])
      if stripped_response != check_result["response"]:
        check_result["type_stripped_response"] = stripped_response

    return check_result


class HttpApiV1RegressionTestMixin(HttpApiRegressionTestMixinBase):
  """Load only API E2E test cases."""

  connection_type = "http_v1"
  skip_legacy_dynamic_proto_tests = False
  api_version = 1

  @property
  def output_file_name(self):
    return os.path.join(DOCUMENT_ROOT,
                        "angular-components/docs/api-docs-examples.json")


class HttpApiV2RegressionTestMixin(HttpApiRegressionTestMixinBase):
  """Load only API E2E test cases."""

  connection_type = "http_v2"
  skip_legacy_dynamic_proto_tests = True
  api_version = 2

  @property
  def output_file_name(self):
    return os.path.join(DOCUMENT_ROOT,
                        "angular-components/docs/api-v2-docs-examples.json")
