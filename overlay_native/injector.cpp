#include <windows.h>
#include <tlhelp32.h>
#include <string>
#include <iostream>

DWORD FindProcessId(const std::wstring& processName) {
    PROCESSENTRY32W entry;
    entry.dwSize = sizeof(PROCESSENTRY32W);
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (Process32FirstW(snapshot, &entry)) {
        do {
            if (!_wcsicmp(entry.szExeFile, processName.c_str())) {
                DWORD pid = entry.th32ProcessID;
                CloseHandle(snapshot);
                return pid;
            }
        } while (Process32NextW(snapshot, &entry));
    }
    CloseHandle(snapshot);
    return 0;
}

int wmain(int argc, wchar_t* argv[]) {
    if (argc < 3) {
        std::wcout << L"Uso: injector.exe <proceso.exe> <ruta\\a\\game_overlay.dll>" << std::endl;
        return 1;
    }
    DWORD pid = FindProcessId(argv[1]);
    if (!pid) {
        std::wcout << L"No se encontró el proceso." << std::endl;
        return 1;
    }
    HANDLE hProcess = OpenProcess(PROCESS_ALL_ACCESS, FALSE, pid);
    if (!hProcess) {
        std::wcout << L"No se pudo abrir el proceso." << std::endl;
        return 1;
    }
    size_t dllPathLen = (wcslen(argv[2]) + 1) * sizeof(wchar_t);
    LPVOID alloc = VirtualAllocEx(hProcess, nullptr, dllPathLen, MEM_COMMIT, PAGE_READWRITE);
    WriteProcessMemory(hProcess, alloc, argv[2], dllPathLen, nullptr);
    HANDLE hThread = CreateRemoteThread(hProcess, nullptr, 0,
        (LPTHREAD_START_ROUTINE)LoadLibraryW, alloc, 0, nullptr);
    WaitForSingleObject(hThread, INFINITE);
    VirtualFreeEx(hProcess, alloc, 0, MEM_RELEASE);
    CloseHandle(hThread);
    CloseHandle(hProcess);
    std::wcout << L"¡Inyección completada!" << std::endl;
    return 0;
}