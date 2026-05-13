import { HttpClient } from '@angular/common/http';

import { inject, Injectable } from '@angular/core';

import { Observable } from 'rxjs';



export interface LibrarySystem {

  id: string;

  name: string;

}



export interface LibraryFolder {

  id: string;

  name: string;

  system_id: string;

}



export interface LibrarySnapshot {

  systems: LibrarySystem[];

  folders: LibraryFolder[];

}



@Injectable({ providedIn: 'root' })

export class LibraryApiService {

  private readonly http = inject(HttpClient);

  private readonly base = '/api/v1/library';



  snapshot(): Observable<LibrarySnapshot> {

    return this.http.get<LibrarySnapshot>(`${this.base}`);

  }



  createSystem(name: string): Observable<LibrarySystem> {

    return this.http.post<LibrarySystem>(`${this.base}/systems`, { name });

  }



  updateSystem(id: string, name: string): Observable<LibrarySystem> {

    return this.http.patch<LibrarySystem>(`${this.base}/systems/${id}`, { name });

  }



  deleteSystem(id: string): Observable<void> {

    return this.http.delete<void>(`${this.base}/systems/${id}`);

  }



  createFolder(name: string, system_id: string): Observable<LibraryFolder> {

    return this.http.post<LibraryFolder>(`${this.base}/folders`, { name, system_id });

  }



  updateFolder(id: string, name: string): Observable<LibraryFolder> {

    return this.http.patch<LibraryFolder>(`${this.base}/folders/${id}`, { name });

  }



  deleteFolder(id: string): Observable<void> {

    return this.http.delete<void>(`${this.base}/folders/${id}`);

  }

}

