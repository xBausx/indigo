// DESCRIPTION: Batch-processes InDesign files in a strict sequence:
// 1. Exports scaled PNG assets.
// 2. Optionally exports a scaled HTML5 document (if supported by InDesign).
// VERSION: Final Stable Automation (Non-Blocking, Dynamic Paths, Accurate Counts)

var SCALE_FACTOR = 8;

// --- Dynamic global paths (portable across PCs) ---
var userDocsFolder = Folder.myDocuments; // e.g., C:/Users/<username>/Documents
var repoBasePath = "/nctv-repositories/indigo";
var OUTPUT_ROOT_PATH = userDocsFolder.fsName + repoBasePath + "/2_Output_HTML";
var COMPLETION_SIGNAL_PATH = userDocsFolder.fsName + repoBasePath + "/resize_complete.txt";

// --- Main function ---
function runSequentialBatchExport() {
    var sourceFolder = Folder.selectDialog("Select the folder containing your InDesign files");
    if (sourceFolder === null) return;

    var outputRootFolder = new Folder(OUTPUT_ROOT_PATH);
    if (!outputRootFolder.exists) outputRootFolder.create();

    var inddFiles = sourceFolder.getFiles("*.indd");
    if (inddFiles.length === 0) {
        $.writeln("No InDesign files were found in the selected folder.");
        writeCompletionSignal(0, 0, []);
        return;
    }

    $.writeln("Found " + inddFiles.length + " files to process in sequence.");
    var totalFilesProcessed = 0;
    var errorLog = [];

    for (var i = 0; i < inddFiles.length; i++) {
        var inddFile = inddFiles[i];
        var doc = null;

        try {
            doc = app.open(inddFile, false);
            var docName = doc.name.replace(/\.indd$/i, "");

            var mainExportFolder = new Folder(outputRootFolder.fsName + "/" + docName);
            if (!mainExportFolder.exists) mainExportFolder.create();

            var imageSubfolder = new Folder(mainExportFolder.fsName + "/publication-web-resources/image");
            if (!imageSubfolder.exists) imageSubfolder.create();

            // --- PNG Export ---
            $.writeln("Starting PNG export for: " + docName);
            exportHighResAssets(doc, imageSubfolder);
            $.writeln("Finished PNG export for: " + docName);

            // --- HTML Export (optional) ---
            try {
                $.writeln("Starting HTML export for: " + docName);
                exportDocumentAsHighResHTML(doc, mainExportFolder);
                $.writeln("Finished HTML export for: " + docName);
            } catch (htmlErr) {
                $.writeln("HTML export skipped or failed for: " + docName + ". Reason: " + htmlErr.message);
            }

            // Count as processed if PNG export succeeded
            totalFilesProcessed++;

        } catch (e) {
            var errorMessage = "ERROR processing " + inddFile.fsName + ": " + e.message;
            $.writeln(errorMessage);
            errorLog.push(errorMessage);
        } finally {
            if (doc !== null) {
                try { doc.close(SaveOptions.NO); }
                catch (closeErr) { $.writeln("Warning: Could not close document: " + closeErr.toString()); }
            }
        }
    }

    writeCompletionSignal(totalFilesProcessed, inddFiles.length, errorLog);
}

// --- Write completion signal for automation ---
function writeCompletionSignal(processed, total, errors) {
    var completionMessage = "Batch complete.\nProcessed " + processed + " of " + total + " files.";
    if (errors.length > 0) {
        completionMessage += "\n\n" + errors.length + " file(s) had errors. Check the JavaScript Console for details.";
    }

    var signalFile = new File(COMPLETION_SIGNAL_PATH);
    signalFile.encoding = "UTF-8";
    if (signalFile.open("w")) {
        signalFile.write(completionMessage);
        signalFile.close();
        $.writeln("Completion signal written to: " + COMPLETION_SIGNAL_PATH);
    } else {
        $.writeln("ERROR: Could not write completion signal to: " + COMPLETION_SIGNAL_PATH);
    }
}

// --- PNG export helper ---
function exportHighResAssets(doc, destinationFolder) {
    var oldFiles = destinationFolder.getFiles();
    for (var f = 0; f < oldFiles.length; f++) {
        try { oldFiles[f].remove(); }
        catch (e) { $.writeln("Couldn't delete: " + oldFiles[f].fsName); }
    }

    app.pngExportPreferences.exportResolution = 72 * SCALE_FACTOR;
    app.pngExportPreferences.pngQuality = PNGQualityEnum.MAXIMUM;
    app.pngExportPreferences.transparentBackground = true;

    var allGraphics = doc.allGraphics;
    if (allGraphics.length === 0) {
        $.writeln("No graphics found in: " + doc.name);
        return;
    }

    for (var i = 0; i < allGraphics.length; i++) {
        var graphic = allGraphics[i];
        var itemToExport = graphic.parent;
        var baseName = "";

        if (graphic.itemLink && graphic.itemLink.isValid && graphic.itemLink.name) {
            baseName = graphic.itemLink.name.replace(/\.[^\.]+$/, "");
        } else {
            baseName = "embedded_asset_" + (i + 1);
        }

        baseName = baseName.replace(/\s/g, "_").replace(/[:\/\\*\?\"\<\>\|]/g, "_");
        var finalFileName = baseName + ".png";
        var filePath = new File(destinationFolder.fsName + "/" + finalFileName);
        var counter = 1;

        while (filePath.exists) {
            finalFileName = baseName + "_" + counter++ + ".png";
            filePath = new File(destinationFolder.fsName + "/" + finalFileName);
        }

        try {
            itemToExport.exportFile(ExportFormat.PNG_FORMAT, filePath, false);
        } catch (e) {
            $.writeln("Failed to export: " + baseName + ". Error: " + e.message);
        }
    }
}

// --- HTML export helper (skips if unsupported) ---
function exportDocumentAsHighResHTML(doc, destinationFolder) {
    if (!app.htmlExportPreferences) {
        $.writeln("HTML export not supported in this InDesign version. Skipping for: " + doc.name);
        return;
    }

    app.htmlExportPreferences.reset();
    app.htmlExportPreferences.viewDocumentAfterExport = false;
    app.htmlExportPreferences.exportSelection = false;
    app.htmlExportPreferences.imageExportResolution = 72 * SCALE_FACTOR;
    app.htmlExportPreferences.imageConversion = ImageConversion.AUTOMATIC;
    app.htmlExportPreferences.imageQuality = ImageQuality.MAXIMUM;

    var docName = doc.name.replace(/\.indd$/i, "");
    var htmlFilePath = new File(destinationFolder.fsName + "/" + docName + ".html");

    try {
        doc.exportFile(ExportFormat.HTML, htmlFilePath, false);
    } catch (e) {
        throw new Error("Failed during HTML export: " + e.message);
    }
}

// --- Execute ---
try {
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
    runSequentialBatchExport();
} catch (e) {
    $.writeln("Critical error: " + e.message);
} finally {
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
}
