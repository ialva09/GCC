(function () {
    "use strict";

    if (!("serviceWorker" in navigator)) {
        return;
    }

    window.addEventListener("load", function () {
        navigator.serviceWorker.register("/service-worker.js", {scope: "/"})
            .catch(function () {
                // Installation is optional; the site remains fully usable online.
            });
    });
}());
