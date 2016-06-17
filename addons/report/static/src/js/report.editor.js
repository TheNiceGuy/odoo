odoo.define('report.editor', function (require) {
"use strict";

var editor = require('web_editor.editor');
var options = require('web_editor.snippets.options');

var is_in_iframe = function () {
    return window.self !== window.top;
};

var post_message = function (message) {
    window.parent.postMessage(message, "http://127.0.0.1:8069");
};

var on_message_received = function (ev) {
    if (ev.source.location.host === window.location.host &&
            ev.source.location.protocol === window.location.protocol) {
        switch(ev.data) {
            case 'report.editor:ask_save':
                console.log('assking save');
                editor.editor_bar.save();
                break;
            case 'report.editor:ask_discard':
                editor.editor_bar.cancel();
                break;
            default:
                console.log('nothing to do for ' + ev.data);
        }
    }
};

if (is_in_iframe()) {
    window.addEventListener('message', on_message_received, false);

    // As editor.reload is called after `save` and `cancel`, we remove this
    // function in the iframe in order to be able to chain deferred after the
    // previously named method.
    editor.reload = function () {
        return $.when();
    };
}

editor.Class.include({
    save: function () {
        // Cannot use `super.then()` as the default implementation triggers a
        // reload of the page.
        // debugger
        var res = this.rte.save();  // FIXME why not _super?
        if (is_in_iframe()) {
            res.then(function () {
                post_message('report.editor:save_ok');
            }, function () {
                post_message('report.editor:save_ko');
            });
        }
        return res;
    },

    cancel: function () {
        var res = this._super.apply(this, arguments);
        if (is_in_iframe()) {
            res.then(function () {
                post_message('report.editor:discard_ok');
            }, function () {
                post_message('report.editor:dicard_ko');
            });
        }
        return res;
    },
});

options.registry.many2one.include({
    select_record: function (li) {
        var self = this;
        this._super(li);
        if (this.$target.data('oe-field') === "partner_id") {
            var $img = $('.header .row img:first');
            var css = window.getComputedStyle($img[0]);
            $img.css("max-height", css.height+'px');
            $img.attr("src", "/web/image/res.partner/"+self.ID+"/image");
            setTimeout(function () { $img.removeClass('o_dirty'); },0);
        }
    }
});

});
