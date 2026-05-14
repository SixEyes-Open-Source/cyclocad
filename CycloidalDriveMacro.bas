Attribute VB_Name = "CycloidalDriveMacro"
Option Explicit

' ============================================================
' Phase 2 - SolidWorks VBA macro skeleton
' - Opens a new part
' - Starts a sketch on the Front Plane
' - Draws a test pitch circle with CreateCircle
' - Imports cycloidal profile from DXF (preferred) or CSV fallback
' ============================================================

' -----------------------------
' Parametric layer (edit here)
' -----------------------------
Public Const GEAR_TEETH As Integer = 25
Public Const GEAR_MODULE_MM As Double = 2#
Public Const R_RATIO As Double = 7.5#
Public Const SAMPLE_COUNT As Integer = 240
Public Const DRAW_TEST_CIRCLE As Boolean = True
Public Const DRAW_CSV_SPLINE As Boolean = True
Public Const DRAW_DXF_SPLINE As Boolean = True
Public Const PREFER_DXF_OVER_CSV As Boolean = True
Public Const CSV_FILE_NAME As String = "strict_cycloidal_gear_outline_points.csv"
Public Const DXF_FILE_NAME As String = "strict_cycloidal_gear_outline_points.dxf"

' SolidWorks sketch coordinates are in meters.
Public Const MM_TO_M As Double = 0.001#

Public Const ORIGIN_X As Double = 0#
Public Const ORIGIN_Y As Double = 0#
Public Const ORIGIN_Z As Double = 0#

Dim swApp As SldWorks.SldWorks
Dim swModel As SldWorks.ModelDoc2
Dim swSketchMgr As SldWorks.SketchManager

Sub main()
    Set swApp = Application.SldWorks

    If swApp Is Nothing Then
        MsgBox "SolidWorks application object is not available.", vbCritical
        Exit Sub
    End If

    If Not NewPartDocument() Then Exit Sub
    If Not StartFrontSketch() Then Exit Sub

    If DRAW_TEST_CIRCLE Then
        DrawTestPitchCircle
    End If

    If PREFER_DXF_OVER_CSV Then
        If DRAW_DXF_SPLINE Then
            If Not DrawCycloidalSplineFromDxf() And DRAW_CSV_SPLINE Then
                If Not DrawCycloidalSplineFromCsv() Then
                    MsgBox "DXF+CSV import failed. Confirm files exist and are valid.", vbExclamation
                End If
            End If
        ElseIf DRAW_CSV_SPLINE Then
            If Not DrawCycloidalSplineFromCsv() Then
                MsgBox "CSV spline import failed. Confirm CSV exists and is valid.", vbExclamation
            End If
        End If
    Else
        If DRAW_CSV_SPLINE Then
            If Not DrawCycloidalSplineFromCsv() And DRAW_DXF_SPLINE Then
                If Not DrawCycloidalSplineFromDxf() Then
                    MsgBox "CSV+DXF import failed. Confirm files exist and are valid.", vbExclamation
                End If
            End If
        ElseIf DRAW_DXF_SPLINE Then
            If Not DrawCycloidalSplineFromDxf() Then
                MsgBox "DXF spline import failed. Confirm DXF exists and is valid.", vbExclamation
            End If
        End If
    End If

    swModel.SketchManager.InsertSketch True
    swModel.ViewZoomtofit2

    MsgBox "Macro complete: sketch created with selected geometry.", vbInformation
End Sub

Private Function NewPartDocument() As Boolean
    Dim partTemplate As String

    partTemplate = swApp.GetUserPreferenceStringValue(swUserPreferenceStringValue_e.swDefaultTemplatePart)
    If Len(partTemplate) = 0 Then
        MsgBox "Default part template is not set in SolidWorks.", vbCritical
        NewPartDocument = False
        Exit Function
    End If

    Set swModel = swApp.NewDocument(partTemplate, 0, 0#, 0#)
    If swModel Is Nothing Then
        MsgBox "Failed to create a new part document.", vbCritical
        NewPartDocument = False
        Exit Function
    End If

    swApp.ActivateDoc3 swModel.GetTitle, False, swRebuildOnActivation_e.swUserDecision, 0
    Set swSketchMgr = swModel.SketchManager

    NewPartDocument = True
End Function

Private Function StartFrontSketch() As Boolean
    Dim ok As Boolean

    ok = swModel.Extension.SelectByID2("Front Plane", "PLANE", 0#, 0#, 0#, False, 0, Nothing, 0)
    If Not ok Then
        MsgBox "Could not select Front Plane.", vbCritical
        StartFrontSketch = False
        Exit Function
    End If

    swSketchMgr.InsertSketch True
    StartFrontSketch = True
End Function

Private Sub DrawTestPitchCircle()
    Dim pitchDiameterMm As Double
    Dim pitchRadiusM As Double

    pitchDiameterMm = GEAR_MODULE_MM * GEAR_TEETH
    pitchRadiusM = (pitchDiameterMm * MM_TO_M) / 2#

    ' CreateCircle(centerX, centerY, centerZ, perimeterX, perimeterY, perimeterZ)
    swSketchMgr.CreateCircle ORIGIN_X, ORIGIN_Y, ORIGIN_Z, pitchRadiusM, 0#, 0#
End Sub

Private Function DrawCycloidalSplineFromCsv() As Boolean
    Dim csvPath As String
    Dim splinePts As Variant
    Dim swSeg As SldWorks.SketchSegment

    csvPath = ResolveCsvPath()
    If Len(csvPath) = 0 Then
        MsgBox "Could not resolve CSV file path.", vbExclamation
        DrawCycloidalSplineFromCsv = False
        Exit Function
    End If

    If Dir$(csvPath) = "" Then
        MsgBox "CSV file not found: " & csvPath, vbExclamation
        DrawCycloidalSplineFromCsv = False
        Exit Function
    End If

    splinePts = LoadSplinePointsFromCsv(csvPath)
    If IsEmpty(splinePts) Then
        MsgBox "CSV did not contain enough points to build a spline.", vbExclamation
        DrawCycloidalSplineFromCsv = False
        Exit Function
    End If

    Set swSeg = swSketchMgr.CreateSpline(splinePts)
    If swSeg Is Nothing Then
        MsgBox "SolidWorks failed to create spline from CSV points.", vbCritical
        DrawCycloidalSplineFromCsv = False
        Exit Function
    End If

    DrawCycloidalSplineFromCsv = True
End Function

Private Function DrawCycloidalSplineFromDxf() As Boolean
    Dim dxfPath As String
    Dim splinePts As Variant
    Dim swSeg As SldWorks.SketchSegment

    dxfPath = ResolveDxfPath()
    If Len(dxfPath) = 0 Then
        DrawCycloidalSplineFromDxf = False
        Exit Function
    End If

    If Dir$(dxfPath) = "" Then
        DrawCycloidalSplineFromDxf = False
        Exit Function
    End If

    splinePts = LoadSplinePointsFromDxf(dxfPath)
    If IsEmpty(splinePts) Then
        DrawCycloidalSplineFromDxf = False
        Exit Function
    End If

    Set swSeg = swSketchMgr.CreateSpline(splinePts)
    If swSeg Is Nothing Then
        DrawCycloidalSplineFromDxf = False
        Exit Function
    End If

    DrawCycloidalSplineFromDxf = True
End Function

Private Function ResolveCsvPath() As String
    Dim macroFolder As String

    macroFolder = swApp.GetCurrentMacroPathFolder()
    If Len(macroFolder) = 0 Then
        ResolveCsvPath = CSV_FILE_NAME
        Exit Function
    End If

    If Right$(macroFolder, 1) = "\" Then
        ResolveCsvPath = macroFolder & CSV_FILE_NAME
    Else
        ResolveCsvPath = macroFolder & "\" & CSV_FILE_NAME
    End If
End Function

Private Function ResolveDxfPath() As String
    Dim macroFolder As String

    macroFolder = swApp.GetCurrentMacroPathFolder()
    If Len(macroFolder) = 0 Then
        ResolveDxfPath = DXF_FILE_NAME
        Exit Function
    End If

    If Right$(macroFolder, 1) = "\" Then
        ResolveDxfPath = macroFolder & DXF_FILE_NAME
    Else
        ResolveDxfPath = macroFolder & "\" & DXF_FILE_NAME
    End If
End Function

Private Function LoadSplinePointsFromCsv(ByVal csvPath As String) As Variant
    Dim ff As Integer
    Dim lineTxt As String
    Dim toks() As String
    Dim vals As Collection
    Dim xM As Double
    Dim yM As Double
    Dim i As Long
    Dim outArr() As Double

    Set vals = New Collection
    ff = FreeFile

    On Error GoTo CsvReadErr
    Open csvPath For Input As #ff

    Do While Not EOF(ff)
        Line Input #ff, lineTxt
        lineTxt = Trim$(lineTxt)

        If Len(lineTxt) = 0 Then
            GoTo ContinueLoop
        End If

        If LCase$(Left$(lineTxt, 5)) = "index" Then
            GoTo ContinueLoop
        End If

        toks = Split(lineTxt, ",")
        If UBound(toks) < 2 Then
            GoTo ContinueLoop
        End If

        xM = Val(Trim$(toks(1))) * MM_TO_M
        yM = Val(Trim$(toks(2))) * MM_TO_M

        vals.Add xM
        vals.Add yM
        vals.Add 0#

ContinueLoop:
    Loop

    Close #ff

    If vals.Count < 9 Then
        LoadSplinePointsFromCsv = Empty
        Exit Function
    End If

    ReDim outArr(0 To vals.Count - 1)
    For i = 1 To vals.Count
        outArr(i - 1) = CDbl(vals(i))
    Next i

    LoadSplinePointsFromCsv = outArr
    Exit Function

CsvReadErr:
    On Error Resume Next
    Close #ff
    LoadSplinePointsFromCsv = Empty
End Function

Private Function LoadSplinePointsFromDxf(ByVal dxfPath As String) As Variant
    Dim ff As Integer
    Dim codeLine As String
    Dim valueLine As String
    Dim vals As Collection
    Dim xMm As Double
    Dim yMm As Double
    Dim haveX As Boolean
    Dim haveY As Boolean
    Dim i As Long
    Dim outArr() As Double

    Set vals = New Collection
    ff = FreeFile

    On Error GoTo DxfReadErr
    Open dxfPath For Input As #ff

    haveX = False
    haveY = False

    Do While Not EOF(ff)
        Line Input #ff, codeLine
        codeLine = Trim$(codeLine)
        If EOF(ff) Then
            Exit Do
        End If

        Line Input #ff, valueLine
        valueLine = Trim$(valueLine)

        If codeLine = "10" Then
            xMm = Val(valueLine)
            haveX = True
        ElseIf codeLine = "20" Then
            yMm = Val(valueLine)
            haveY = True
        End If

        If haveX And haveY Then
            vals.Add xMm * MM_TO_M
            vals.Add yMm * MM_TO_M
            vals.Add 0#
            haveX = False
            haveY = False
        End If
    Loop

    Close #ff

    If vals.Count < 9 Then
        LoadSplinePointsFromDxf = Empty
        Exit Function
    End If

    ReDim outArr(0 To vals.Count - 1)
    For i = 1 To vals.Count
        outArr(i - 1) = CDbl(vals(i))
    Next i

    LoadSplinePointsFromDxf = outArr
    Exit Function

DxfReadErr:
    On Error Resume Next
    Close #ff
    LoadSplinePointsFromDxf = Empty
End Function
