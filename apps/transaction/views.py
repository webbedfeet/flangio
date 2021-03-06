#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4
import os, uuid, json
from django.conf import settings
from django.shortcuts import render_to_response
from django.contrib import messages
from django.http import HttpResponse, Http404, HttpResponseRedirect
from ..accounts.models import flangioUser as User
from django.template import RequestContext
from django.core.context_processors import csrf
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime, timedelta
from django.core.urlresolvers import reverse
from django.contrib.auth.decorators import login_required
from ..accounts.decorators import json_login_required, access_required
from ..accounts.models import Permission
from forms import *
from utils import *
from xls_utils import convert_to_xls, convert_to_csv, convert_labels_to_xls
from models import Transaction, DataLabelMeta
from dict2xml import dict2xml
from django.db import IntegrityError

@json_login_required
@csrf_exempt
def build_keys(request):
    """Perform the map/reduce to refresh the keys form. The display the custom report screen"""
    x = build_keys_with_mapreduce()
    messages.success(request, "Successfully completed MapReduce operation. Key rebuild for custom report complete.")
    return HttpResponseRedirect(reverse("home_index"))


@json_login_required
@csrf_exempt
def custom_report(request):
    ckeys = get_collection_keys()

    if request.method == 'POST':
        form = KeysForm(ckeys, get_collection_labels(), request.POST)
        if form.is_valid():
            return_keys=[]
            data = form.cleaned_data
            for k,v in data.items():
                if v==True:
                    return_keys.append(k)

            q = massage_dates(json.loads(data['query']))

            if data['outputformat']=="xls":
                return search_xls(request, collection=None, return_keys=return_keys,
                                   query=json.loads(data['query']))
            elif data['outputformat']=="csv":
                return search_csv(request, collection=None, return_keys=return_keys,
                                   query=json.loads(data['query']))
            elif data['outputformat']=="xml":
                return search_xml(request, collection=None, return_keys=return_keys,
                                   query=json.loads(data['query']))
            else:
                return search_json(request, collection=None, return_keys=return_keys,
                                   query=json.loads(data['query']))

        else:

            return render_to_response('search/select-keys.html', {'form': form},
                RequestContext(request))

    #Get the distinct keys from the collection
    ckeys = get_collection_keys()

    #get the labels
    label_dict = get_collection_labels()

    return render_to_response('search/select-keys.html',
         {'form': KeysForm(ckeys, label_dict),}, RequestContext(request))











@csrf_exempt
@json_login_required
@access_required('delete-transactions')
def delete_transaction(request):
    if request.method == 'POST':
        form = DeleteTransactionForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            invalid_response ={"message":
                        "No transaction was deleted. The transaction delete failed due to the following error(s).",
                        "code": 500,
                        "errors": []}

            result = delete_tx(data)

            if int(result['code']) != 200:
                if result.has_key('errors'):
                    invalid_response['errors'].append(result['errors'])
                jsonstr={"code": int(result['code']),
                                 "message": result['message'],
                                 "errors": result['errors']}
            else:
                jsonstr={"code": 200,
                                 "message": "Transaction deleted."}

            jsonstr=json.dumps(jsonstr, indent = 4,)
            return HttpResponse(jsonstr, mimetype="application/json")
        else:
            # the form had errors
            errors=[]
            if form.non_field_errors():
                global_error={'global':global_error}
                errors.append()

        for k,v in form._errors.items():
            error={'field': k, 'description':v}
            errors.append(error)

        jsonstr={"code": 500,
                         "message": "No transaction was deleted. The transaction delete failed due to the following error(s). ",
                         "errors": errors}
        jsonstr=json.dumps(jsonstr, indent = 4,)
        return HttpResponse(jsonstr, status=500, mimetype="application/json")


    #this is an HTTP GET
    return render_to_response('transaction/delete.html',
        {'form': DeleteTransactionForm(),'STATIC_URL':settings.STATIC_URL}, RequestContext(request))















@json_login_required
@csrf_exempt
def create_transaction(request):
    if request.method == 'POST':
        form = TransactionForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data

            invalid_response ={"message": "No transaction was created. The transaction failed due to the following error(s).",
                               "code": 500,
                               "errors": []}
            if data.has_key('points'):

                if data['points']:
                    try:
                        p=Permission.objects.get(user=request.user,
                                                permission_name='assign-points')

                    except(Permission.DoesNotExist):
                        invalid_response['errors'].append("You do not have permission to assign points.")
                        invalid_response['code'] = 401
                        jsonstr=json.dumps(invalid_response, indent = 4,)
                        return HttpResponse(jsonstr, mimetype="application/json")



            if settings.USERS_MUST_EXIST:
                data = verify_users_exist_and_sg(data)

                if data.has_key('errors'):
                    invalid_response['errors'].append(data['errors'])
                    jsonstr=json.dumps(invalid_response, indent = 4,)
                    return HttpResponse(jsonstr, mimetype="application/json")

            tx=Transaction(**data)
            result=tx.save()

            if int(result['code']) != 200:
                #print "result =", result
                jsonstr={"code": int(result['code']),
                         "message": result['message'],
                         "errors": result['errors']}
            else:
                jsonstr={"code": 200,
                         "message": "Transaction created.",
                         "results": (result['results'],)}

                jsonstr=json.dumps(jsonstr, indent = 4,)
                return HttpResponse(jsonstr, mimetype="application/json")
        else:
            # the form had errors
            errors=[]
        if form.non_field_errors():
            global_error={'global':global_error}
            errors.append()


        for k,v in form._errors.items():
            error={'field': k, 'description':v}
            errors.append(error)
            jsonstr={"code": 500,
                     "message": "No transaction was created. The transaction failed due to the following error(s). ",
                     "errors": errors}
            jsonstr=json.dumps(jsonstr, indent = 4,)
            return HttpResponse(jsonstr, status=500, mimetype="application/json")

    #this is an HTTP GET
    return render_to_response('transaction/create.html',
        {'form': TransactionForm(),}, RequestContext(request))


@json_login_required
def get_by_transaction_id(request, txid):

    searchkeys={'_id': txid}
    result = query_mongo_db(searchkeys)
    # print result
    if int(result['code'])==200:
        listresults=result['results']
    if settings.RESPECT_SOCIAL_GRAPH:
        listresults=filter_social_graph(request, listresults)

        result['results']=listresults
        return HttpResponse(to_json(result), status=result['code'],
                             mimetype="application/json")
    else:

        return HttpResponse(to_json(result), status=result['code'],
                             mimetype="application/json")

@json_login_required
def get_history_by_transaction_id(request, txid):

    searchkeys={'_id': txid}
    result = query_mongo_db(searchkeys, "history")


    if int(result['status'])==200:
        listresults=result['results']
    if settings.RESPECT_SOCIAL_GRAPH:
        listresults=filter_social_graph(request, listresults)

        result['results']=listresults
        jsonresults=to_json(result)
        return HttpResponse(jsonresults, status=result['status'])
    else:
        jsonresults=to_json(result)
        return HttpResponse(jsonresults, status=result['status'])






@json_login_required
def get_since_id(request, sinceid):
    searchkeys={ "since_id" : { '$gt': sinceid } }

    pass






@json_login_required
def search_json(request, collection=None, return_keys=(), query={}):

    if not query:
        kwargs = {}
        for k,v in request.GET.items():
            kwargs[k]=v
    else:
        kwargs = query

    result = query_mongo(kwargs, collection, return_keys=return_keys)

    if int(result['code'])==200:
        listresults=result['results']

    else:
        response = json.dumps(result, indent =4)
        return HttpResponse(response, status=int(result['code']),
                            mimetype="application/json")

    if settings.RESPECT_SOCIAL_GRAPH:
        listresults=filter_social_graph(request, listresults)


        len_results=len(listresults)
        if len_results < result['num_results']:
            result['ommitted-results']= result['num_results'] - len_results
            result['results']=listresults

        jsonresults=to_json(result)
        return HttpResponse(jsonresults, status=int(result['code']),
                            mimetype="application/json")
    else:
        jsonresults=to_json(normalize_results(result))
        return HttpResponse(jsonresults, status=int(result['code']),mimetype="application/json")


@json_login_required
def search_xml(request, collection=None, return_keys=(), query={}):

    if not query:
        kwargs = {}
        for k,v in request.GET.items():
            kwargs[k]=v
    else:
        kwargs = query

    result = query_mongo(kwargs, collection, return_keys=return_keys)

    if int(result['code'])==200:
        listresults=result['results']

    else:
        response = dict2xml({"flangio":result})
        return HttpResponse(response, status=int(result['code']),
                            mimetype="application/xml")

    if settings.RESPECT_SOCIAL_GRAPH:
        listresults=filter_social_graph(request, listresults)


        len_results=len(listresults)
        if len_results < result['num_results']:
            result['ommitted-results']= result['num_results'] - len_results
            result['results']=listresults

        xmlresults=dict2xml({"flangio":result})
        return HttpResponse(xmlresults, status=int(result['code']),
                            mimetype="application/xml")
    else:
        xmlresults=dict2xml({"flangio":normalize_results(result)})
        return HttpResponse(xmlresults, status=int(result['code']),
                            mimetype="application/xml")


@json_login_required
def search_history_json(request):
    return search_json(request, "history")



@json_login_required
def search_xls(request, collection=None, return_keys=(), query={}):

    if not query:
        kwargs = {}
        for k,v in request.GET.items():
            kwargs[k]=v
    else:
        kwargs = query

    result = query_mongo(kwargs, collection, return_keys=return_keys)

    if int(result['code']) == 200:
        listresults=result['results']

        if settings.RESPECT_SOCIAL_GRAPH:
            listresults = filter_social_graph(request, listresults)
            len_results = len(listresults)
            if len_results < result['num_results']:
                result['ommitted-results']= result['num_results'] - len_results

        keylist = []

        for i in listresults:
            for j in i.keys():
                if not keylist.__contains__(j):
                    keylist.append(j)


        return convert_to_xls(keylist, normalize_list(listresults))

    else:
        jsonresults=to_json(result)
        return HttpResponse(jsonresults, status=int(result['code']),
                            mimetype="application/json")


@json_login_required
def search_csv(request, collection=None, return_keys=(), query={}):

    if not query:
        kwargs = {}
        for k,v in request.GET.items():
            kwargs[k]=v
    else:
        kwargs = query

    result = query_mongo(kwargs, collection, return_keys=return_keys)

    #print result.keys()

    if int(result['code']) == 200:
        listresults=result['results']
        if settings.RESPECT_SOCIAL_GRAPH:
            listresults = filter_social_graph(request, listresults)
            len_results = len(listresults)
            if len_results < result['num_results']:
                result['ommitted-results']= result['num_results'] - len_results

        keylist = []
        for i in listresults:
            for j in i.keys():
                if not keylist.__contains__(j):
                    keylist.append(j)


        return convert_to_csv(keylist, listresults)

    else:
        jsonresults=to_json(result)
        return HttpResponse(jsonresults, status=int(result['code']),
                            mimetype="application/json")


@json_login_required
def get_my_transactions_by_type(request,txtype=""):

    #if request.method == 'GET':
    #    jsonstr={"status": "405",
    #             "message": "This method is Not implemented or not allowed. Try a POST"}
    #    jsonstr=json.dumps(jsonstr, indent = 4,)
    #    return HttpResponse( jsonstr, status=405)

    attrs={}
    for attr in request.POST:
        #print "%s=%s" % (attr,request.POST[attr])
        """load our attrs dict with request.POST attrs"""
        attrs[attr]=request.POST[attr]
    attrs['transaction_type']=txtype

    #print attrs

    searchkeys=attrs
    result = query_mongo_db(searchkeys, "history")
    #print result


    if int(result['code'])==200:
        listresults=result['results']
        if settings.RESPECT_SOCIAL_GRAPH:
            listresults=filter_social_graph(request, listresults)

        result['results']=listresults
        jsonresults=to_json(result)
        return HttpResponse(jsonresults, status=result['status'])
    else:
        jsonresults=to_json(result)
        return HttpResponse(jsonresults, status=result['status'])
