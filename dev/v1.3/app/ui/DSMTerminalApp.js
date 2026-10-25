Ext.ns("SYNO.SDS.App.DSMTerminal");

var DSM_TERMINAL_VERSION = "0.1.3-4";

SYNO.SDS.App.DSMTerminal = Ext.extend(SYNO.SDS.AppWindow, {
    constructor: function () {
        this.windowId = Ext.id(null, "dsm-terminal-window-");
        this.panelId = Ext.id(null, "dsm-terminal-panel-");
        this.iframeId = Ext.id(null, "dsm-terminal-frame-");

        SYNO.SDS.App.DSMTerminal.superclass.constructor.call(this, {
            id: this.windowId,
            width: 620,
            height: 420,
            minWidth: 420,
            minHeight: 300,
            maximizable: true,
            resizable: true,
            layout: "fit",
            title: "DSM Terminal",
            cls: "dsm-terminal-window",
            tools: [
                {
                    id: "help",
                    handler: this.onHelpToolClick,
                    scope: this
                }
            ],
            items: [
                {
                    xtype: "panel",
                    id: this.panelId,
                    border: false,
                    layout: "fit",
                    html: '<iframe id="' + this.iframeId + '" data-window-id="' + this.windowId + '" src="/webman/3rdparty/dsm-terminal/index.html?v=' + DSM_TERMINAL_VERSION + '" style="display:block;width:100%;height:100%;border:0;background:#ffffff;"></iframe>'
                }
            ],
            listeners: {
                show: this.bindFrameActivation,
                activate: this.onParentActivate,
                deactivate: this.onParentDeactivate,
                hide: this.hideHelpWindow,
                minimize: this.hideHelpWindow,
                beforedestroy: this.beforeWindowDestroy,
                scope: this
            }
        });

        this.helpWindow = null;
        this.helpVisibleWithParent = false;
        this.helpWindowActive = false;
        this.helpWindowOpening = false;
        this.boundWindowMessage = this.onWindowMessage.createDelegate(this);
    },

    bindFrameActivation: function () {
        var frame = Ext.get(this.iframeId);
        if (!frame) {
            return;
        }

        frame.removeAllListeners();
        frame.on("load", this.attachFrameListeners, this);
        this.attachFrameListeners();
        if (window.addEventListener) {
            window.removeEventListener("message", this.boundWindowMessage, false);
            window.addEventListener("message", this.boundWindowMessage, false);
        }
    },

    beforeWindowDestroy: function () {
        if (this.helpWindow && !this.helpWindow.isDestroyed) {
            this.helpWindow.close();
            this.helpWindow = null;
        }
        if (window.removeEventListener) {
            window.removeEventListener("message", this.boundWindowMessage, false);
        }
    },

    hideHelpWindow: function () {
        if (this.helpWindow && !this.helpWindow.isDestroyed) {
            this.helpVisibleWithParent = this.helpWindow.isVisible();
            this.helpWindow.hide();
        }
    },

    onParentActivate: function () {
        this.focusTerminalFrame();

        if (!this.helpWindow || this.helpWindow.isDestroyed || !this.helpVisibleWithParent) {
            return;
        }

        this.helpWindow.show();
        this.helpWindow.toFront.defer(1, this.helpWindow);
    },

    onParentDeactivate: function () {
        if (!this.helpWindow || this.helpWindow.isDestroyed) {
            return;
        }

        if (this.helpWindowActive || this.helpWindowOpening) {
            return;
        }

        this.helpVisibleWithParent = this.helpWindow.isVisible();
        this.helpWindow.hide();
    },

    attachFrameListeners: function () {
        var frame = document.getElementById(this.iframeId);
        var doc;
        var win;
        var activate = this.activateFromFrame.createDelegate(this);

        if (!frame) {
            return;
        }

        frame.onclick = activate;
        frame.onmousedown = activate;

        try {
            win = frame.contentWindow;
            doc = win && win.document;
            if (!doc) {
                return;
            }

            doc.onclick = activate;
            doc.onmousedown = activate;
            if (doc.body) {
                doc.body.onclick = activate;
                doc.body.onmousedown = activate;
            }
        } catch (e) {
        }
    },

    activateFromFrame: function () {
        this.toFront();
        this.setActive();
        this.onParentActivate();
    },

    focusTerminalFrame: function () {
        var frame = document.getElementById(this.iframeId);

        if (!frame || !frame.contentWindow || !frame.contentWindow.postMessage) {
            return;
        }

        try {
            frame.contentWindow.postMessage({
                type: "dsm-terminal-focus",
                windowId: this.windowId
            }, "*");
        } catch (e) {
        }
    },

    onHelpToolClick: function () {
        this.openHelpWindow();
    },

    onWindowMessage: function (event) {
        var data = event && event.data;
        if (!data) {
            return;
        }
        if (data.type === "dsm-terminal-open-help") {
            if (data.windowId && data.windowId !== this.windowId) {
                return;
            }
            this.openHelpWindow();
            return;
        }
        if (data.type === "dsm-terminal-pty-closed") {
            if (data.windowId && data.windowId !== this.windowId) {
                return;
            }
            this.close();
            return;
        }
        if (data.type === "dsm-terminal-help-size" && this.helpWindow && !this.helpWindow.isDestroyed) {
            if (data.windowId && data.windowId !== this.windowId) {
                return;
            }
            this.resizeHelpWindow(data.height);
            return;
        }
        if (data.type === "dsm-terminal-font-change") {
            if (data.windowId && data.windowId !== this.windowId) {
                return;
            }
            var frame = document.getElementById(this.iframeId);
            if (frame && frame.contentWindow && frame.contentWindow.postMessage) {
                frame.contentWindow.postMessage({
                    type: "dsm-terminal-font-change",
                    windowId: this.windowId,
                    fontFamily: data.fontFamily
                }, "*");
            }
            return;
        }
        if (data.type === "dsm-terminal-close-help" && this.helpWindow && !this.helpWindow.isDestroyed) {
            this.helpWindow.close();
        }
    },

    resizeHelpWindow: function (height) {
        if (!this.helpWindow || this.helpWindow.isDestroyed || !height) {
            return;
        }

        var targetHeight = Math.max(220, Math.min(420, parseInt(height, 10) || 0));
        if (!targetHeight) {
            return;
        }

        if (Math.abs(this.helpWindow.getSize().height - targetHeight) < 12) {
            return;
        }

        this.helpWindow.setHeight(targetHeight);
        this.helpWindow.doLayout();
    },

    openHelpWindow: function () {
        if (this.helpWindow && !this.helpWindow.isDestroyed) {
            this.helpWindowOpening = true;
            this.helpVisibleWithParent = true;
            this.helpWindow.show();
            this.helpWindow.center();
            this.helpWindow.toFront();
            window.setTimeout(function () {
                this.helpWindowOpening = false;
            }.createDelegate(this), 150);
            return;
        }

        this.helpWindow = new SYNO.SDS.Window({
            id: Ext.id(null, "dsm-terminal-help-window-"),
            title: "DSM Terminal Help",
            width: 520,
            height: 260,
            minWidth: 420,
            minHeight: 220,
            minimizable: false,
            maximizable: false,
            resizable: false,
            modal: false,
            owner: this,
            manager: this.manager || Ext.WindowMgr,
            layout: "fit",
            closable: true,
            dsmStyle: "v5",
            plain: false,
            shadow: true,
            border: true,
            constrainHeader: true,
            cls: "sds-window-v5 active-win dsm-terminal-help-window",
            bodyStyle: "background:#f3f5f9;",
            items: [
                {
                    xtype: "panel",
                    border: false,
                    layout: "fit",
                    html: '<iframe src="/webman/3rdparty/dsm-terminal/help.html?v=' + DSM_TERMINAL_VERSION + '" data-window-id="' + this.windowId + '" style="display:block;width:100%;height:100%;border:0;background:#f3f5f9;"></iframe>'
                }
            ],
            listeners: {
                activate: function () {
                    this.helpWindowActive = true;
                    this.helpWindowOpening = false;
                },
                deactivate: function () {
                    this.helpWindowActive = false;
                },
                show: function () {
                    this.helpVisibleWithParent = true;
                },
                hide: function () {
                    this.helpWindowActive = false;
                    this.helpWindowOpening = false;
                    this.helpVisibleWithParent = false;
                },
                close: function () {
                    this.helpWindow = null;
                    this.helpWindowActive = false;
                    this.helpWindowOpening = false;
                    this.helpVisibleWithParent = false;
                },
                scope: this
            }
        });

        this.helpWindowOpening = true;
        this.helpVisibleWithParent = true;
        this.helpWindow.show();
        this.helpWindow.center();
        this.helpWindow.toFront.defer(1, this.helpWindow);
        window.setTimeout(function () {
            this.helpWindowOpening = false;
        }.createDelegate(this), 150);
    }
});

SYNO.SDS.App.DSMTerminal.Instance = Ext.extend(SYNO.SDS.AppInstance, {
    appWindowName: "SYNO.SDS.App.DSMTerminal"
});
