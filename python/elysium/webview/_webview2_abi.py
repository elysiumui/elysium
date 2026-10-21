"""WebView2 COM ABI used by the Windows backend: vtable slots and IIDs.

Taken from WebView2.h of the pinned Microsoft.Web.WebView2 SDK.
scripts/fetch-webview2-loader.py re-checks every entry against that
header whenever it fetches the loader, so a wrong slot fails the build
instead of calling the wrong method. Pure data: importable anywhere."""

SDK_VERSION = "1.0.4258.31"

#: interface -> method -> vtable slot (0-2 are IUnknown).
SLOTS: dict[str, dict[str, int]] = {
    "ICoreWebView2": {
        "get_Settings": 3,
        "Navigate": 5,
        "NavigateToString": 6,
        "add_NavigationCompleted": 15,
        "add_ProcessFailed": 25,
        "AddScriptToExecuteOnDocumentCreated": 27,
        "RemoveScriptToExecuteOnDocumentCreated": 28,
        "ExecuteScript": 29,
        "CapturePreview": 30,
        "Reload": 31,
        "add_WebMessageReceived": 34,
        "get_CanGoBack": 38,
        "get_CanGoForward": 39,
        "GoBack": 40,
        "GoForward": 41,
        "Stop": 43,
        "add_WebResourceRequested": 55,
        "AddWebResourceRequestedFilter": 57,
    },
    "ICoreWebView2_21": {
        "ExecuteScriptWithResult": 122,
    },
    "ICoreWebView2Controller": {
        "put_IsVisible": 4,
        "put_Bounds": 6,
        "Close": 24,
        "get_CoreWebView2": 25,
    },
    "ICoreWebView2Controller2": {
        "put_DefaultBackgroundColor": 27,
    },
    "ICoreWebView2Controller3": {
        "put_RasterizationScale": 29,
        "put_ShouldDetectMonitorScaleChanges": 31,
        "put_BoundsMode": 35,
    },
    "ICoreWebView2Environment": {
        "CreateCoreWebView2Controller": 3,
        "CreateWebResourceResponse": 4,
    },
    "ICoreWebView2Settings": {
        "put_IsStatusBarEnabled": 10,
        "put_AreDefaultContextMenusEnabled": 14,
        "put_IsZoomControlEnabled": 18,
    },
    "ICoreWebView2Settings2": {
        "put_UserAgent": 22,
    },
    "ICoreWebView2NavigationCompletedEventArgs": {
        "get_IsSuccess": 3,
        "get_WebErrorStatus": 4,
    },
    "ICoreWebView2WebMessageReceivedEventArgs": {
        "TryGetWebMessageAsString": 5,
    },
    "ICoreWebView2ExecuteScriptResult": {
        "get_Succeeded": 3,
        "get_ResultAsJson": 4,
        "get_Exception": 6,
    },
    "ICoreWebView2ScriptException": {
        "get_Name": 5,
        "get_Message": 6,
    },
    "ICoreWebView2WebResourceRequestedEventArgs": {
        "get_Request": 3,
        "put_Response": 5,
    },
    "ICoreWebView2WebResourceRequest": {
        "get_Uri": 3,
    },
    "ICoreWebView2ProcessFailedEventArgs": {
        "get_ProcessFailedKind": 3,
    },
}

IIDS: dict[str, str] = {
    "ICoreWebView2_21": "c4980dea-587b-43b9-8143-3ef3bf552d95",
    "ICoreWebView2Controller2": "c979903e-d4ca-4228-92eb-47ee3fa96eab",
    "ICoreWebView2Controller3": "f9614724-5d2b-41dc-aef7-73d62b51543b",
    "ICoreWebView2Settings2": "ee9a0f68-f46c-4e32-ac23-ef8cac224d2a",
    "ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler": "4e8a3389-c9d8-4bd2-b6b5-124fee6cc14d",
    "ICoreWebView2CreateCoreWebView2ControllerCompletedHandler": "6c4819f3-c9b7-4260-8127-c9f5bde7f68c",
    "ICoreWebView2ExecuteScriptCompletedHandler": "49511172-cc67-4bca-9923-137112f4c4cc",
    "ICoreWebView2ExecuteScriptWithResultCompletedHandler": "1bb5317b-8238-4c67-a7ff-baf6558f289d",
    "ICoreWebView2CapturePreviewCompletedHandler": "697e05e9-3d8f-45fa-96f4-8ffe1ededaf5",
    "ICoreWebView2AddScriptToExecuteOnDocumentCreatedCompletedHandler": "b99369f3-9b11-47b5-bc6f-8e7895fcea17",
    "ICoreWebView2NavigationCompletedEventHandler": "d33a35bf-1c49-4f98-93ab-006e0533fe1c",
    "ICoreWebView2WebMessageReceivedEventHandler": "57213f19-00e6-49fa-8e07-898ea01ecbd2",
    "ICoreWebView2ProcessFailedEventHandler": "79e0aea4-990b-42d9-aa1d-0fcc2e5bc7f1",
    "ICoreWebView2WebResourceRequestedEventHandler": "ab00b74c-15f1-4646-80e8-e76341d25d71",
}
