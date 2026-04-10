import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule, Routes } from '@angular/router';
import { BusinessesComponent } from './businesses.component';

const routes: Routes = [
  { path: '', component: BusinessesComponent }
];

@NgModule({
  declarations: [BusinessesComponent],
  imports: [
    CommonModule,
    RouterModule.forChild(routes),
  ]
})
export class BusinessesModule {}
