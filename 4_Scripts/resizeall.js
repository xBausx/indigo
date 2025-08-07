// DESCRIPTION: Batch-processes InDesign files for Project Indigo.
// VERSION: 3.3 (Final Merged - Alert Signal)

// --- CONFIGURATION ---
var SCALE_FACTOR = 8;
var userDocsFolder = Folder.myDocuments;
var repoBasePath = "/nctv-repositories/indigo";
var OUTPUT_ROOT_PATH = userDocsFolder.fsName + repoBasePath + "/2_Output_HTML";
// COMPLETION_SIGNAL_PATH is no longer needed.

// --- MAIN FUNCTION ---
function runSequentialBatchExport() {
    var sourceFolder = Folder.selectDialog("Select the folder containing your InDesign files");
    if (sourceFolder === null) return;

    var outputRootFolder = new Folder(OUTPUT_ROOT_PATH);
    if (!outputRootFolder.exists) outputRootFolder.create();

    var inddFiles = sourceFolder.getFiles("*.indd");
    if (inddFiles.length === 0) {
        // We still need to signal completion even if no files were processed.
        alert("INDIGO_RESIZE_COMPLETE");
        return;
    }

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

            exportHighResAssets(doc, imageSubfolder);
            exportDocumentAsHighResHTML(doc, mainExportFolder);

            totalFilesProcessed++;

        } catch (e) {
            var errorMessage = "ERROR processing " + inddFile.name + ": " + e.message;
            $.writeln(errorMessage);
            errorLog.push(errorMessage);
        } finally {
            if (doc !== null) {
                doc.close(SaveOptions.NO);
            }
        }
    }
    
    // --- NEW COMPLETION SIGNAL ---
    // Instead of writing a file, we now show a simple, unique alert.
    // Our Python script will wait for this specific alert to appear.
    alert("INDIGO_RESIZE_COMPLETE");
}

// The writeCompletionSignal function has been removed.

// --- PNG EXPORT HELPER (Your proven, working code) ---
function exportHighResAssets(doc, destinationFolder) {
    var oldFiles = destinationFolder.getFiles();
    for (var f = 0; f < oldFiles.length; f++) {
        try { oldFiles[f].remove(); } catch (e) {}
    }

    app.pngExportPreferences.exportResolution = 72 * SCALE_FACTOR;
    app.pngExportPreferences.pngQuality = PNGQualityEnum.MAXIMUM;
    app.pngExportPreferences.transparentBackground = true;

    var allGraphics = doc.allGraphics;
    if (allGraphics.length === 0) return;

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
        
        try {
            itemToExport.exportFile(ExportFormat.PNG_FORMAT, filePath, false);
            $.writeln("Exported: " + finalFileName);
        } catch (e) {
            $.writeln("Failed to export: " + finalFileName + " — " + e.message);
        }
    }
}

// --- HTML EXPORT HELPER (Your proven, working code) ---
function exportDocumentAsHighResHTML(doc, destinationFolder) {
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

// --- EXECUTION BLOCK ---
try {
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.NEVER_INTERACT;
    runSequentialBatchExport();
} catch (e) {
    $.writeln("Critical error: " + e.message);
} finally {
    app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
}